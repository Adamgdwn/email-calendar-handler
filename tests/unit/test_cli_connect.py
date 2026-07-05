from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import pytest

from src.cli import (
    CONSENT_LOG_FILENAME,
    EXIT_CONFIG_ERROR,
    EXIT_FAILURE,
    EXIT_OK,
    TOKEN_CACHE_FILENAME,
    main,
)
from src.ingestion.graph_auth import MicrosoftGraphOAuthSettings
from src.ingestion.graph_token_cache import DeviceFlowClient, TokenCacheState
from src.models.auth_models import OAuthConsentRecord
from src.models.email_models import Provider
from src.utils.encryption import FieldEncryptor

SUCCESS_FLOW: dict[str, Any] = {
    "user_code": "ABC123",
    "device_code": "synthetic-device-code",
    "verification_uri": "https://microsoft.com/devicelogin",
    "message": "To sign in, open https://microsoft.com/devicelogin and enter the code ABC123.",
}
SUCCESS_RESULT: dict[str, Any] = {
    "access_token": "synthetic-access-token",
    "scope": "User.Read Mail.Read",
    "id_token_claims": {
        "preferred_username": "adam@example.com",
        "oid": "00000000-0000-0000-0000-000000000001",
        "tid": "11111111-1111-1111-1111-111111111111",
    },
}


class FakeDeviceFlowClient:
    def __init__(
        self,
        flow: dict[str, Any] | None = None,
        flow_result: dict[str, Any] | None = None,
    ) -> None:
        self.flow = flow if flow is not None else dict(SUCCESS_FLOW)
        self.flow_result = flow_result if flow_result is not None else dict(SUCCESS_RESULT)
        self.cache: TokenCacheState | None = None

    def get_accounts(self, username: str | None = None) -> list[dict[str, Any]]:
        return []

    def acquire_token_silent(
        self, scopes: list[str], account: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return None

    def initiate_device_flow(self, scopes: list[str]) -> dict[str, Any]:
        return self.flow

    def acquire_token_by_device_flow(self, flow: dict[str, Any]) -> dict[str, Any]:
        if "access_token" in self.flow_result and self.cache is not None:
            self.cache.has_state_changed = True
        return self.flow_result


def make_factory(fake: FakeDeviceFlowClient, calls: list[TokenCacheState]) -> Any:
    def factory(settings: MicrosoftGraphOAuthSettings, cache: TokenCacheState) -> DeviceFlowClient:
        calls.append(cache)
        fake.cache = cache
        return fake

    return factory


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in (
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET",
        "MICROSOFT_TENANT_ID",
        "MICROSOFT_REDIRECT_URI",
        "MICROSOFT_SCOPES",
        "ENCRYPTION_KEY_BASE64",
        "INBOXMIND_HOME",
    ):
        monkeypatch.delenv(key, raising=False)
    home_dir = tmp_path / "inboxmind-home"
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    monkeypatch.setenv("ENCRYPTION_KEY_BASE64", FieldEncryptor.generate_key().decode("utf-8"))
    monkeypatch.setenv("INBOXMIND_HOME", str(home_dir))
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    return home_dir


def test_connect_success_writes_consent_and_encrypted_cache(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeDeviceFlowClient()
    calls: list[TokenCacheState] = []

    exit_code = main(["connect"], client_factory=make_factory(fake, calls))

    captured = capsys.readouterr().out
    assert exit_code == EXIT_OK
    assert len(calls) == 1
    assert "ABC123" in captured
    assert SUCCESS_RESULT["access_token"] not in captured

    consent_path = home / CONSENT_LOG_FILENAME
    record = OAuthConsentRecord.model_validate_json(consent_path.read_text().strip())
    assert record.provider is Provider.MICROSOFT_GRAPH
    assert record.subject == "adam@example.com"
    assert record.scopes == ["User.Read", "Mail.Read"]
    assert record.tenant_id == "11111111-1111-1111-1111-111111111111"
    assert record.account_type == "organizational"
    assert record.human_confirmed is True
    assert stat.S_IMODE(consent_path.stat().st_mode) == 0o600

    cache_path = home / TOKEN_CACHE_FILENAME
    assert cache_path.exists()
    assert b"synthetic" not in cache_path.read_bytes()
    assert stat.S_IMODE(cache_path.stat().st_mode) == 0o600


def test_connect_declined_leaves_no_side_effects(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    calls: list[TokenCacheState] = []

    exit_code = main(["connect"], client_factory=make_factory(FakeDeviceFlowClient(), calls))

    assert exit_code == EXIT_FAILURE
    assert "Aborted" in capsys.readouterr().out
    assert not calls
    assert not home.exists()


def test_connect_device_flow_failure_reports_and_fails(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeDeviceFlowClient(
        flow={"error": "invalid_client", "error_description": "public client flows disabled"}
    )
    calls: list[TokenCacheState] = []

    exit_code = main(["connect"], client_factory=make_factory(fake, calls))

    captured = capsys.readouterr().out
    assert exit_code == EXIT_FAILURE
    assert "Connection failed" in captured
    assert "public client flows disabled" in captured
    assert not (home / CONSENT_LOG_FILENAME).exists()


def test_connect_missing_encryption_key_is_config_error(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ENCRYPTION_KEY_BASE64")
    calls: list[TokenCacheState] = []

    exit_code = main(["connect"], client_factory=make_factory(FakeDeviceFlowClient(), calls))

    captured = capsys.readouterr().out
    assert exit_code == EXIT_CONFIG_ERROR
    assert "ENCRYPTION_KEY_BASE64" in captured
    assert not calls


def test_connect_invalid_encryption_key_is_config_error(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY_BASE64", "not-a-valid-key")
    calls: list[TokenCacheState] = []

    exit_code = main(["connect"], client_factory=make_factory(FakeDeviceFlowClient(), calls))

    captured = capsys.readouterr().out
    assert exit_code == EXIT_CONFIG_ERROR
    assert "Fernet" in captured
    assert not calls


def test_connect_missing_client_id_is_config_error(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MICROSOFT_CLIENT_ID")
    calls: list[TokenCacheState] = []

    exit_code = main(["connect"], client_factory=make_factory(FakeDeviceFlowClient(), calls))

    captured = capsys.readouterr().out
    assert exit_code == EXIT_CONFIG_ERROR
    assert "MICROSOFT_CLIENT_ID" in captured
    assert not calls
