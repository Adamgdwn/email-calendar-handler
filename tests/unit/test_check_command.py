"""Tests for `inboxmind check` — CRITICAL-filter logic and already-notified dedup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from src.cli import CHECK_NOTIFIED_FILENAME, CHECK_WINDOW_HOURS, main
from src.ingestion.graph_delta import build_initial_delta_url
from tests.fakes import FakeTableGateway, ScriptedGraphTransport, empty_calendar_script

CLEARED = (
    "ANTHROPIC_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
    "MICROSOFT_CLIENT_ID",
    "MICROSOFT_TENANT_ID",
    "MICROSOFT_CLIENT_SECRET",
    "MICROSOFT_REDIRECT_URI",
    "ENCRYPTION_KEY_BASE64",
    "INBOXMIND_HOME",
    "INBOXMIND_ACCOUNTS",
)

DELTA_LINK_CHECK = "https://graph.microsoft.com/v1.0/delta?token=check"


class RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def notify(self, subjects: list[str]) -> None:
        self.calls.append(list(subjects))


@pytest.fixture
def check_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in CLEARED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENCRYPTION_KEY_BASE64", Fernet.generate_key().decode())
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "synthetic-client-id")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "common")
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-key")
    home = tmp_path / "home"
    monkeypatch.setenv("INBOXMIND_HOME", str(home))
    return home


def _mock_client(subject: str = "check@example.com") -> Any:
    client = MagicMock()
    client.get_accounts.return_value = [{"username": subject}]
    client.acquire_token_silent.return_value = {
        "access_token": "synthetic-token",
        "scope": "Mail.Read User.Read",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    return client


def _mock_client_factory(subject: str = "check@example.com") -> Any:
    client = _mock_client(subject)
    return lambda *_a, **_kw: client


def _empty_sync_transport() -> ScriptedGraphTransport:
    """Empty delta + empty calendar — sync writes nothing new."""
    return ScriptedGraphTransport(
        {
            build_initial_delta_url(): {"value": [], "@odata.deltaLink": DELTA_LINK_CHECK},
            DELTA_LINK_CHECK: {"value": [], "@odata.deltaLink": DELTA_LINK_CHECK},
            **empty_calendar_script(),
        }
    )


def _seed_email(
    gateway: FakeTableGateway,
    *,
    urgency: str,
    subject: str,
    msg_id: str,
    hours_ago: float = 0.5,
) -> None:
    ts = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()
    gateway.insert_rows(
        "emails",
        [
            {
                "id": msg_id,
                "account_id": "fake-account-id",
                "thread_id": f"thread-{msg_id}",
                "subject": subject,
                "urgency": urgency,
                "message_timestamp": ts,
                "sender_email": "sender@example.com",
                "body_ciphertext": "",
                "body_hash": f"hash-{msg_id}",
                "labels": ["INBOX"],
                "classification": {},
                "provider_message_id": f"pm-{msg_id}",
            }
        ],
    )


# ── exit code ─────────────────────────────────────────────────────────────────


def test_check_no_critical_items_exits_ok(check_env: Path) -> None:
    gateway = FakeTableGateway()
    _seed_email(gateway, urgency="normal", subject="Normal mail", msg_id="msg-001")
    notifier = RecordingNotifier()

    exit_code = main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    assert exit_code == 0
    assert notifier.calls == []


def test_check_without_cached_token_exits_ok(check_env: Path) -> None:
    client = MagicMock()
    client.get_accounts.return_value = []  # no cached accounts → token not found

    notifier = RecordingNotifier()
    exit_code = main(
        ["check"],
        client_factory=lambda *_a, **_kw: client,
        gateway_factory=lambda _s: FakeTableGateway(),
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    assert exit_code == 0
    assert notifier.calls == []


# ── CRITICAL filter ───────────────────────────────────────────────────────────


def test_check_critical_item_triggers_notification(check_env: Path) -> None:
    gateway = FakeTableGateway()
    _seed_email(gateway, urgency="critical", subject="Urgent contract", msg_id="msg-crit-001")
    notifier = RecordingNotifier()

    main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    assert len(notifier.calls) == 1
    assert "Urgent contract" in notifier.calls[0]


def test_check_only_critical_urgency_band_notifies(check_env: Path) -> None:
    gateway = FakeTableGateway()
    _seed_email(gateway, urgency="critical", subject="CRIT", msg_id="msg-c")
    _seed_email(gateway, urgency="high", subject="HIGH", msg_id="msg-h")
    _seed_email(gateway, urgency="normal", subject="NORM", msg_id="msg-n")
    _seed_email(gateway, urgency="low", subject="LOW", msg_id="msg-l")
    notifier = RecordingNotifier()

    main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    assert len(notifier.calls) == 1
    subjects = notifier.calls[0]
    assert "CRIT" in subjects
    assert "HIGH" not in subjects
    assert "NORM" not in subjects
    assert "LOW" not in subjects


def test_check_old_critical_outside_window_not_notified(check_env: Path) -> None:
    gateway = FakeTableGateway()
    _seed_email(
        gateway,
        urgency="critical",
        subject="Old contract",
        msg_id="msg-old",
        hours_ago=CHECK_WINDOW_HOURS + 1.0,
    )
    notifier = RecordingNotifier()

    main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    assert notifier.calls == []


def test_check_multiple_critical_items_in_one_notification(check_env: Path) -> None:
    gateway = FakeTableGateway()
    _seed_email(gateway, urgency="critical", subject="First CRIT", msg_id="msg-c1")
    _seed_email(gateway, urgency="critical", subject="Second CRIT", msg_id="msg-c2")
    notifier = RecordingNotifier()

    main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    assert len(notifier.calls) == 1
    assert len(notifier.calls[0]) == 2


# ── dedup ─────────────────────────────────────────────────────────────────────


def test_check_already_notified_id_skipped(check_env: Path) -> None:
    gateway = FakeTableGateway()
    _seed_email(gateway, urgency="critical", subject="Already seen", msg_id="msg-seen")
    check_env.mkdir(parents=True, exist_ok=True)
    (check_env / CHECK_NOTIFIED_FILENAME).write_text("msg-seen\n", encoding="utf-8")

    notifier = RecordingNotifier()
    main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    assert notifier.calls == []


def test_check_new_critical_id_appended_to_dedup_file(check_env: Path) -> None:
    gateway = FakeTableGateway()
    _seed_email(gateway, urgency="critical", subject="New CRITICAL", msg_id="msg-new")
    notifier = RecordingNotifier()

    main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    notified_path = check_env / CHECK_NOTIFIED_FILENAME
    assert notified_path.exists()
    ids = {
        line.strip()
        for line in notified_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert "msg-new" in ids


def test_check_second_run_deduplicates_notified_ids(check_env: Path) -> None:
    """Running check twice on the same CRITICAL item notifies only on the first run."""
    gateway = FakeTableGateway()
    _seed_email(gateway, urgency="critical", subject="Once only", msg_id="msg-once")
    notifier = RecordingNotifier()

    main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )
    main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    assert len(notifier.calls) == 1  # second run skips the already-notified ID


def test_check_partial_dedup_notifies_only_new_ids(check_env: Path) -> None:
    gateway = FakeTableGateway()
    _seed_email(gateway, urgency="critical", subject="Old seen", msg_id="msg-old")
    _seed_email(gateway, urgency="critical", subject="New one", msg_id="msg-new2")
    check_env.mkdir(parents=True, exist_ok=True)
    (check_env / CHECK_NOTIFIED_FILENAME).write_text("msg-old\n", encoding="utf-8")

    notifier = RecordingNotifier()
    main(
        ["check"],
        client_factory=_mock_client_factory(),
        gateway_factory=lambda _s: gateway,
        transport_factory=_empty_sync_transport,
        notifier=notifier,
    )

    assert len(notifier.calls) == 1
    assert "New one" in notifier.calls[0]
    assert "Old seen" not in notifier.calls[0]
