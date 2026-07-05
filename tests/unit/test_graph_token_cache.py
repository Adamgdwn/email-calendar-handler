from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import msal
import pytest

from src.ingestion.graph_auth import GRAPH_REQUIRED_SCOPES, MicrosoftGraphOAuthSettings
from src.ingestion.graph_token_cache import (
    MSA_CONSUMER_TENANT_ID,
    DeviceCodePrompt,
    DeviceFlowClient,
    EncryptedTokenCache,
    GraphAuthenticator,
    GraphAuthError,
    TokenCacheState,
    msal_request_scopes,
)
from src.utils.encryption import FieldEncryptor

SYNTHETIC_CACHE_STATE = '{"AccessToken": {"entry": {"secret": "synthetic-cache-entry"}}}'
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
        *,
        accounts: list[dict[str, Any]] | None = None,
        silent_result: dict[str, Any] | None = None,
        flow: dict[str, Any] | None = None,
        flow_result: dict[str, Any] | None = None,
    ) -> None:
        self.accounts = accounts or []
        self.silent_result = silent_result
        self.flow = flow if flow is not None else dict(SUCCESS_FLOW)
        self.flow_result = flow_result if flow_result is not None else dict(SUCCESS_RESULT)
        self.silent_scopes: list[str] | None = None
        self.device_scopes: list[str] | None = None
        self.cache: TokenCacheState | None = None

    def get_accounts(self, username: str | None = None) -> list[dict[str, Any]]:
        return self.accounts

    def acquire_token_silent(
        self, scopes: list[str], account: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        self.silent_scopes = scopes
        return self.silent_result

    def initiate_device_flow(self, scopes: list[str]) -> dict[str, Any]:
        self.device_scopes = scopes
        return self.flow

    def acquire_token_by_device_flow(self, flow: dict[str, Any]) -> dict[str, Any]:
        if "access_token" in self.flow_result and self.cache is not None:
            self.cache.has_state_changed = True
        return self.flow_result


@pytest.fixture
def graph_settings(monkeypatch: pytest.MonkeyPatch) -> MicrosoftGraphOAuthSettings:
    for key in (
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET",
        "MICROSOFT_TENANT_ID",
        "MICROSOFT_REDIRECT_URI",
        "MICROSOFT_SCOPES",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    return MicrosoftGraphOAuthSettings()


def make_store(tmp_path: Path) -> EncryptedTokenCache:
    return EncryptedTokenCache(
        tmp_path / "graph_token_cache.enc",
        FieldEncryptor(FieldEncryptor.generate_key()),
    )


def make_authenticator(
    settings: MicrosoftGraphOAuthSettings,
    store: EncryptedTokenCache,
    fake: FakeDeviceFlowClient,
) -> GraphAuthenticator:
    def factory(settings: MicrosoftGraphOAuthSettings, cache: TokenCacheState) -> DeviceFlowClient:
        fake.cache = cache
        return fake

    return GraphAuthenticator(settings, store, factory)


def test_token_cache_round_trip_is_encrypted_at_rest(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    cache = msal.SerializableTokenCache()
    cache.deserialize(SYNTHETIC_CACHE_STATE)
    cache.has_state_changed = True

    store.save(cache)

    raw = store.path.read_bytes()
    assert b"synthetic-cache-entry" not in raw
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    loaded = store.load()
    assert loaded.serialize() == cache.serialize()


def test_token_cache_save_skips_when_state_unchanged(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.save(msal.SerializableTokenCache())

    assert not store.path.exists()


def test_token_cache_load_without_file_returns_empty_cache(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    loaded = store.load()

    assert loaded.serialize() == msal.SerializableTokenCache().serialize()


def test_msal_request_scopes_filters_reserved_scopes() -> None:
    assert msal_request_scopes(GRAPH_REQUIRED_SCOPES) == ["User.Read", "Mail.Read"]


def test_device_flow_success(tmp_path: Path, graph_settings: MicrosoftGraphOAuthSettings) -> None:
    store = make_store(tmp_path)
    fake = FakeDeviceFlowClient()
    authenticator = make_authenticator(graph_settings, store, fake)
    prompts: list[DeviceCodePrompt] = []

    result = authenticator.acquire_token(prompts.append)

    assert result.access_token.get_secret_value() == SUCCESS_RESULT["access_token"]
    assert result.subject == "adam@example.com"
    assert result.account_id == (
        "00000000-0000-0000-0000-000000000001.11111111-1111-1111-1111-111111111111"
    )
    assert result.tenant_id == "11111111-1111-1111-1111-111111111111"
    assert result.account_type == "organizational"
    assert result.scopes == ("User.Read", "Mail.Read")
    assert result.from_cache is False
    assert prompts[0].user_code == "ABC123"
    assert fake.device_scopes == ["User.Read", "Mail.Read"]
    assert SUCCESS_RESULT["access_token"] not in repr(result)
    assert store.path.exists()
    assert b"synthetic" not in store.path.read_bytes()


def test_silent_token_served_from_cache(
    tmp_path: Path, graph_settings: MicrosoftGraphOAuthSettings
) -> None:
    fake = FakeDeviceFlowClient(
        accounts=[{"username": "adam@example.com"}],
        silent_result=dict(SUCCESS_RESULT),
    )
    authenticator = make_authenticator(graph_settings, make_store(tmp_path), fake)

    result = authenticator.acquire_token(lambda prompt: None)

    assert result.from_cache is True
    assert fake.silent_scopes == ["User.Read", "Mail.Read"]
    assert fake.device_scopes is None


def test_silent_miss_falls_back_to_device_flow(
    tmp_path: Path, graph_settings: MicrosoftGraphOAuthSettings
) -> None:
    fake = FakeDeviceFlowClient(
        accounts=[{"username": "adam@example.com"}],
        silent_result=None,
    )
    authenticator = make_authenticator(graph_settings, make_store(tmp_path), fake)

    result = authenticator.acquire_token(lambda prompt: None)

    assert result.from_cache is False
    assert fake.device_scopes == ["User.Read", "Mail.Read"]


def test_device_flow_initiation_failure_raises(
    tmp_path: Path, graph_settings: MicrosoftGraphOAuthSettings
) -> None:
    fake = FakeDeviceFlowClient(
        flow={"error": "invalid_client", "error_description": "public client flows disabled"}
    )
    authenticator = make_authenticator(graph_settings, make_store(tmp_path), fake)

    with pytest.raises(GraphAuthError, match="public client flows disabled"):
        authenticator.acquire_token(lambda prompt: None)


def test_device_flow_token_failure_raises(
    tmp_path: Path, graph_settings: MicrosoftGraphOAuthSettings
) -> None:
    fake = FakeDeviceFlowClient(
        flow_result={"error": "access_denied", "error_description": "user declined consent"}
    )
    authenticator = make_authenticator(graph_settings, make_store(tmp_path), fake)

    with pytest.raises(GraphAuthError, match="user declined consent"):
        authenticator.acquire_token(lambda prompt: None)


def test_personal_account_detected_from_consumer_tenant(
    tmp_path: Path, graph_settings: MicrosoftGraphOAuthSettings
) -> None:
    result_payload = dict(SUCCESS_RESULT)
    result_payload["id_token_claims"] = {
        "preferred_username": "adam@example.com",
        "oid": "00000000-0000-0000-0000-000000000002",
        "tid": MSA_CONSUMER_TENANT_ID,
    }
    fake = FakeDeviceFlowClient(flow_result=result_payload)
    authenticator = make_authenticator(graph_settings, make_store(tmp_path), fake)

    result = authenticator.acquire_token(lambda prompt: None)

    assert result.account_type == "personal"


def test_missing_claims_fall_back_to_requested_scopes(
    tmp_path: Path, graph_settings: MicrosoftGraphOAuthSettings
) -> None:
    fake = FakeDeviceFlowClient(flow_result={"access_token": SUCCESS_RESULT["access_token"]})
    authenticator = make_authenticator(graph_settings, make_store(tmp_path), fake)

    result = authenticator.acquire_token(lambda prompt: None)

    assert result.subject == "unknown"
    assert result.account_id == "unknown"
    assert result.tenant_id is None
    assert result.account_type is None
    assert result.scopes == GRAPH_REQUIRED_SCOPES
