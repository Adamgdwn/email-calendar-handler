from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from src.cli import main
from src.ingestion.graph_auth import MicrosoftGraphOAuthSettings
from src.ingestion.graph_delta import build_initial_delta_url
from src.ingestion.graph_token_cache import DeviceFlowClient, TokenCacheState
from src.memory.supabase_client import SupabaseSettings, TableGateway
from tests.fakes import FakeTableGateway, ScriptedGraphTransport, graph_message, make_consent

SILENT_RESULT: dict[str, Any] = {
    "access_token": "synthetic-access-token",
    "scope": "User.Read Mail.Read",
    "id_token_claims": {
        "preferred_username": "owner@example.com",
        "oid": "00000000-0000-0000-0000-000000000001",
        "tid": "11111111-1111-1111-1111-111111111111",
    },
}


class SilentOnlyClient:
    """Fake msal client with a cached account; sync must never start a device flow."""

    def get_accounts(self, username: str | None = None) -> list[dict[str, Any]]:
        return [{"home_account_id": "synthetic-home-account"}]

    def acquire_token_silent(
        self, scopes: list[str], account: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return dict(SILENT_RESULT)

    def initiate_device_flow(self, scopes: list[str]) -> dict[str, Any]:
        raise AssertionError("sync must never start a device flow")

    def acquire_token_by_device_flow(self, flow: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("sync must never start a device flow")


class NoAccountClient(SilentOnlyClient):
    def get_accounts(self, username: str | None = None) -> list[dict[str, Any]]:
        return []


def silent_client_factory(
    settings: MicrosoftGraphOAuthSettings, cache: TokenCacheState
) -> DeviceFlowClient:
    return SilentOnlyClient()


def no_account_client_factory(
    settings: MicrosoftGraphOAuthSettings, cache: TokenCacheState
) -> DeviceFlowClient:
    return NoAccountClient()


@pytest.fixture
def sync_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for key in (
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET",
        "MICROSOFT_TENANT_ID",
        "MICROSOFT_REDIRECT_URI",
        "MICROSOFT_SCOPES",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "ENCRYPTION_KEY_BASE64",
        "INBOXMIND_HOME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)  # keep any developer .env out of settings loading
    home = tmp_path / "inboxmind-home"
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "synthetic-client-id")
    monkeypatch.setenv("ENCRYPTION_KEY_BASE64", Fernet.generate_key().decode())
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-service-role-key")
    monkeypatch.setenv("INBOXMIND_HOME", str(home))
    return home


def test_sync_happy_path_stores_encrypted_mail(
    sync_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    consent_path = sync_env / "consent_log.jsonl"
    consent_path.parent.mkdir(parents=True)
    consent_path.write_text(make_consent().model_dump_json() + "\n", encoding="utf-8")
    gateway = FakeTableGateway()
    transport = ScriptedGraphTransport(
        {
            build_initial_delta_url(): {
                "value": [graph_message("m-0001", body="Body one")],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?token=one",
            }
        }
    )

    exit_code = main(
        ["sync"],
        client_factory=silent_client_factory,
        gateway_factory=lambda settings: gateway,
        transport_factory=lambda: transport,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Synced owner@example.com" in output
    assert "1 stored encrypted" in output
    assert "synthetic-access-token" not in output
    emails = gateway.tables["emails"]
    assert len(emails) == 1
    assert emails[0]["body_ciphertext"] != "Body one"
    assert len(gateway.tables["account_consents"]) == 1
    assert transport.closed is True


def test_sync_without_cached_token_directs_to_connect(
    sync_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def unused_gateway(settings: SupabaseSettings) -> TableGateway:
        raise AssertionError("gateway must not be constructed without a cached token")

    exit_code = main(
        ["sync"],
        client_factory=no_account_client_factory,
        gateway_factory=unused_gateway,
        transport_factory=lambda: ScriptedGraphTransport({}),
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "inboxmind connect" in output


def test_sync_missing_supabase_settings_exits_config_error(
    sync_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SUPABASE_URL")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")

    exit_code = main(["sync"], client_factory=silent_client_factory)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "SUPABASE_URL" in output


def test_sync_blank_supabase_url_is_config_error(
    sync_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "")

    exit_code = main(["sync"], client_factory=silent_client_factory)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "SUPABASE_URL" in output
