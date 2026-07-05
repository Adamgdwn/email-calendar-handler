"""CLI tests for `inboxmind review` against the in-memory gateway."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.cli import main
from src.memory.account_store import ensure_account
from src.memory.supabase_client import SupabaseSettings, TableGateway
from src.models.email_models import Provider
from src.utils.encryption import FieldEncryptor
from tests.fakes import FakeTableGateway

CLEARED_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
    "MICROSOFT_CLIENT_ID",
    "MICROSOFT_TENANT_ID",
    "ENCRYPTION_KEY_BASE64",
    "INBOXMIND_HOME",
    "INBOXMIND_ENV",
)


@pytest.fixture
def review_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in CLEARED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENCRYPTION_KEY_BASE64", Fernet.generate_key().decode())
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-service-role-key")
    home = tmp_path / "home"
    monkeypatch.setenv("INBOXMIND_HOME", str(home))
    return home


def scripted_input(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    stream: Iterator[str] = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(stream))


def seed_mailbox(gateway: FakeTableGateway) -> str:
    encryptor = FieldEncryptor(os.environ["ENCRYPTION_KEY_BASE64"].encode("utf-8"))
    account_id = ensure_account(
        gateway,
        provider=Provider.MICROSOFT_GRAPH,
        primary_email="owner@example.com",
        display_name="Owner",
        org_type="organizational",
        scopes=["User.Read", "Mail.Read"],
    )
    now = datetime.now(tz=UTC)
    gateway.insert_rows(
        "emails",
        [
            {
                "account_id": account_id,
                "thread_id": f"thread-{index}",
                "provider_message_id": f"m-{index}",
                "sender_email": "client@clientfirm.example",
                "subject": f"Proposal {index}",
                "body_ciphertext": encryptor.encrypt_text("Synthetic body."),
                "body_hash": f"hash-{index}",
                "message_timestamp": (now - timedelta(hours=1)).isoformat(),
                "labels": ["INBOX"],
                "urgency": None,
                "classification": {},
            }
            for index in range(3)
        ],
    )
    return account_id


def unused_gateway(_settings: SupabaseSettings) -> TableGateway:
    msg = "gateway must not be built when configuration is invalid"
    raise AssertionError(msg)


def test_review_accept_all_confirms_a_rule(
    review_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeTableGateway()
    seed_mailbox(gateway)
    scripted_input(monkeypatch, ["a", "a", "a"])

    exit_code = main(["review", "--profile", "consulting"], gateway_factory=lambda _s: gateway)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Reviewed 3 proposal(s)" in output
    assert "3 accepted" in output
    assert "Promoted to confirmed: Review" in output

    rules = gateway.rows("filing_rules")
    assert len(rules) == 1
    assert rules[0]["status"] == "confirmed"
    assert rules[0]["human_approved"] is False


def test_review_skip_all_records_nothing(
    review_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeTableGateway()
    seed_mailbox(gateway)
    scripted_input(monkeypatch, ["s", "s", "s"])

    exit_code = main(["review", "--profile", "consulting"], gateway_factory=lambda _s: gateway)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Reviewed 0 proposal(s)" in output
    assert gateway.rows("feedback") == []


def test_review_rejects_non_positive_hours(
    review_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["review", "--hours", "0"], gateway_factory=unused_gateway)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "--hours" in output


def test_review_without_account_exits_failure(
    review_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        ["review", "--profile", "consulting"], gateway_factory=lambda _s: FakeTableGateway()
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "inboxmind sync" in output
