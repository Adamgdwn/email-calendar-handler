"""CLI tests for `inboxmind brief` against the in-memory gateway."""

import os
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
    "GMAIL_CLIENT_ID",
    "GMAIL_CLIENT_SECRET",
    "MICROSOFT_CLIENT_ID",
    "MICROSOFT_TENANT_ID",
    "MICROSOFT_CLIENT_SECRET",
    "MICROSOFT_REDIRECT_URI",
    "ENCRYPTION_KEY_BASE64",
    "INBOXMIND_HOME",
    "INBOXMIND_ENV",
)


@pytest.fixture
def brief_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in CLEARED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # keep any developer .env out of settings loading
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENCRYPTION_KEY_BASE64", Fernet.generate_key().decode())
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-service-role-key")
    home = tmp_path / "home"
    monkeypatch.setenv("INBOXMIND_HOME", str(home))
    return home


def build_encryptor_from_env() -> FieldEncryptor:
    return FieldEncryptor(os.environ["ENCRYPTION_KEY_BASE64"].encode("utf-8"))


def seed_mailbox(gateway: FakeTableGateway, encryptor: FieldEncryptor) -> str:
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
                "thread_id": "thread-critical",
                "provider_message_id": "m-0001",
                "sender_email": "client@clientfirm.example",
                "subject": "Contract deadline for the proposal",
                "body_ciphertext": encryptor.encrypt_text("The contract deadline is tomorrow."),
                "body_hash": "hash-0001",
                "message_timestamp": (now - timedelta(hours=2)).isoformat(),
                "labels": ["INBOX"],
                "urgency": None,
                "classification": {},
            },
            {
                "account_id": account_id,
                "thread_id": "thread-low",
                "provider_message_id": "m-0002",
                "sender_email": "news@bulletin.example",
                "subject": "Community newsletter",
                "body_ciphertext": encryptor.encrypt_text("Nothing that needs action."),
                "body_hash": "hash-0002",
                "message_timestamp": (now - timedelta(hours=3)).isoformat(),
                "labels": ["INBOX"],
                "urgency": None,
                "classification": {},
            },
        ],
    )
    return account_id


def unused_gateway(_settings: SupabaseSettings) -> TableGateway:
    msg = "gateway must not be built when configuration is invalid"
    raise AssertionError(msg)


def test_brief_happy_path_classifies_persists_and_writes_file(
    brief_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeTableGateway()
    seed_mailbox(gateway, build_encryptor_from_env())

    exit_code = main(["brief", "--profile", "consulting"], gateway_factory=lambda _s: gateway)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "# Morning Brief" in output
    assert "## Critical" in output
    assert "Contract deadline for the proposal" in output
    assert "2 classified now" in output

    emails = gateway.rows("emails")
    assert all(row["urgency"] is not None for row in emails)
    assert all(row["classification"] for row in emails)
    assert all(row["sender_taxonomy"] == "external_unknown" for row in emails)

    consulting_row = next(
        row for row in gateway.rows("personas") if row["profile_id"] == "consulting"
    )
    assert gateway.rows("accounts")[0]["persona_id"] == consulting_row["id"]

    brief_files = list((brief_env / "briefs").glob("brief-*.md"))
    assert len(brief_files) == 1
    assert "# Morning Brief" in brief_files[0].read_text(encoding="utf-8")


def test_second_brief_run_reclassifies_nothing(
    brief_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeTableGateway()
    seed_mailbox(gateway, build_encryptor_from_env())

    assert main(["brief", "--profile", "consulting"], gateway_factory=lambda _s: gateway) == 0
    first_classifications = [dict(row)["classification"] for row in gateway.rows("emails")]
    capsys.readouterr()

    assert main(["brief"], gateway_factory=lambda _s: gateway) == 0

    output = capsys.readouterr().out
    assert "0 classified now" in output
    assert "2 already classified" in output
    assert [dict(row)["classification"] for row in gateway.rows("emails")] == first_classifications


def test_brief_without_profile_on_placeholder_persona_exits_config_error(
    brief_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeTableGateway()
    seed_mailbox(gateway, build_encryptor_from_env())

    exit_code = main(["brief"], gateway_factory=lambda _s: gateway)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "--profile" in output
    assert "consulting" in output


def test_brief_with_unknown_profile_exits_config_error(
    brief_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeTableGateway()
    seed_mailbox(gateway, build_encryptor_from_env())

    exit_code = main(["brief", "--profile", "nonexistent"], gateway_factory=lambda _s: gateway)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Unknown profile 'nonexistent'" in output


def test_brief_without_account_exits_failure(
    brief_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["brief"], gateway_factory=lambda _s: FakeTableGateway())

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "inboxmind sync" in output


def test_brief_missing_supabase_settings_exits_config_error(
    brief_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SUPABASE_URL")

    exit_code = main(["brief"], gateway_factory=unused_gateway)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "SUPABASE_URL" in output


def test_brief_rejects_non_positive_hours(
    brief_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["brief", "--hours", "0"], gateway_factory=unused_gateway)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "--hours" in output
