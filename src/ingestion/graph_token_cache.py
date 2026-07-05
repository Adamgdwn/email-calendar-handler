from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import msal
from pydantic import BaseModel, Field, SecretStr

from src.ingestion.graph_auth import MicrosoftGraphOAuthSettings
from src.models.auth_models import AccountType
from src.utils.encryption import FieldEncryptor

MSAL_RESERVED_SCOPES = frozenset({"openid", "profile", "offline_access"})
MSA_CONSUMER_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"


class GraphAuthError(RuntimeError):
    """Raised when Microsoft Graph token acquisition fails."""


class TokenCacheState(Protocol):
    has_state_changed: bool

    def serialize(self) -> str: ...

    def deserialize(self, state: str) -> None: ...


class DeviceFlowClient(Protocol):
    """Structural subset of msal.PublicClientApplication used by InboxMind."""

    def get_accounts(self, username: str | None = None) -> list[dict[str, Any]]: ...

    def acquire_token_silent(
        self, scopes: list[str], account: dict[str, Any] | None
    ) -> dict[str, Any] | None: ...

    def initiate_device_flow(self, scopes: list[str]) -> dict[str, Any]: ...

    def acquire_token_by_device_flow(self, flow: dict[str, Any]) -> dict[str, Any]: ...


ClientFactory = Callable[[MicrosoftGraphOAuthSettings, TokenCacheState], DeviceFlowClient]


class DeviceCodePrompt(BaseModel):
    message: str = Field(min_length=1)
    verification_uri: str = Field(min_length=1)
    user_code: str = Field(min_length=1)


class GraphTokenResult(BaseModel):
    access_token: SecretStr
    subject: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    tenant_id: str | None = None
    account_type: AccountType | None = None
    scopes: tuple[str, ...] = Field(min_length=1)
    from_cache: bool


class EncryptedTokenCache:
    """Persists the MSAL token cache as Fernet ciphertext; plaintext never touches disk."""

    def __init__(self, path: Path, encryptor: FieldEncryptor) -> None:
        self._path = path
        self._encryptor = encryptor

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> TokenCacheState:
        cache: TokenCacheState = msal.SerializableTokenCache()
        if self._path.exists():
            ciphertext = self._path.read_text(encoding="utf-8")
            cache.deserialize(self._encryptor.decrypt_text(ciphertext))
        return cache

    def save(self, cache: TokenCacheState) -> None:
        if not cache.has_state_changed:
            return
        ciphertext = self._encryptor.encrypt_text(cache.serialize())
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(ciphertext)


def msal_request_scopes(scopes: tuple[str, ...]) -> list[str]:
    """MSAL injects the OIDC reserved scopes itself and rejects explicit requests for them."""
    return [scope for scope in scopes if scope not in MSAL_RESERVED_SCOPES]


def build_msal_client(
    settings: MicrosoftGraphOAuthSettings, cache: TokenCacheState
) -> DeviceFlowClient:
    client: DeviceFlowClient = msal.PublicClientApplication(
        settings.client_id,
        authority=settings.authority,
        token_cache=cache,
    )
    return client


class GraphAuthenticator:
    """Acquires delegated read-only Graph tokens: silent from the encrypted cache
    first, interactive device-code flow second."""

    def __init__(
        self,
        settings: MicrosoftGraphOAuthSettings,
        cache_store: EncryptedTokenCache,
        client_factory: ClientFactory = build_msal_client,
    ) -> None:
        self._settings = settings
        self._cache_store = cache_store
        self._client_factory = client_factory

    def acquire_token(
        self, on_device_prompt: Callable[[DeviceCodePrompt], None]
    ) -> GraphTokenResult:
        cache = self._cache_store.load()
        client = self._client_factory(self._settings, cache)
        scopes = msal_request_scopes(self._settings.scopes)
        result = self._acquire_silent(client, scopes)
        from_cache = result is not None
        if result is None:
            result = self._acquire_by_device_flow(client, scopes, on_device_prompt)
        self._cache_store.save(cache)
        return self._to_token_result(result, from_cache=from_cache)

    def acquire_cached_token(self) -> GraphTokenResult | None:
        """Silent-only acquisition for non-interactive commands; None means sign in first."""
        cache = self._cache_store.load()
        client = self._client_factory(self._settings, cache)
        result = self._acquire_silent(client, msal_request_scopes(self._settings.scopes))
        if result is None:
            return None
        self._cache_store.save(cache)
        return self._to_token_result(result, from_cache=True)

    def _acquire_silent(self, client: DeviceFlowClient, scopes: list[str]) -> dict[str, Any] | None:
        accounts = client.get_accounts()
        if not accounts:
            return None
        result = client.acquire_token_silent(scopes, accounts[0])
        if result is None or "access_token" not in result:
            return None
        # Silent/cached results often omit id_token_claims; inject the MSAL account
        # username so _to_token_result can always resolve a valid email subject.
        account_username = accounts[0].get("username", "")
        if account_username and "id_token_claims" not in result:
            result = {**result, "_account_username": account_username}
        return result

    def _acquire_by_device_flow(
        self,
        client: DeviceFlowClient,
        scopes: list[str],
        on_device_prompt: Callable[[DeviceCodePrompt], None],
    ) -> dict[str, Any]:
        flow = client.initiate_device_flow(scopes)
        if "user_code" not in flow or "verification_uri" not in flow:
            msg = f"device flow initiation failed: {_error_detail(flow)}"
            raise GraphAuthError(msg)
        verification_uri = str(flow["verification_uri"])
        user_code = str(flow["user_code"])
        message = str(
            flow.get("message")
            or f"To sign in, open {verification_uri} and enter the code {user_code}."
        )
        on_device_prompt(
            DeviceCodePrompt(
                message=message,
                verification_uri=verification_uri,
                user_code=user_code,
            )
        )
        result = client.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            msg = f"device flow token acquisition failed: {_error_detail(result)}"
            raise GraphAuthError(msg)
        return result

    def _to_token_result(self, result: dict[str, Any], *, from_cache: bool) -> GraphTokenResult:
        claims_raw = result.get("id_token_claims")
        claims: dict[str, Any] = claims_raw if isinstance(claims_raw, dict) else {}
        subject = str(
            claims.get("preferred_username")
            or claims.get("email")
            or claims.get("upn")
            or result.get("_account_username")
            or "unknown"
        )
        object_id = claims.get("oid")
        tenant_id = claims.get("tid") if isinstance(claims.get("tid"), str) else None
        account_id = (
            f"{object_id}.{tenant_id}" if isinstance(object_id, str) and tenant_id else subject
        )
        account_type: AccountType | None = None
        if tenant_id is not None:
            account_type = "personal" if tenant_id == MSA_CONSUMER_TENANT_ID else "organizational"
        scope_raw = result.get("scope")
        granted_scopes = (
            tuple(scope_raw.split())
            if isinstance(scope_raw, str) and scope_raw.strip()
            else tuple(self._settings.scopes)
        )
        return GraphTokenResult(
            access_token=SecretStr(str(result["access_token"])),
            subject=subject,
            account_id=account_id,
            tenant_id=tenant_id,
            account_type=account_type,
            scopes=granted_scopes,
            from_cache=from_cache,
        )


def _error_detail(payload: dict[str, Any]) -> str:
    return str(payload.get("error_description") or payload.get("error") or "unknown error")
