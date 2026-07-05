"""InboxMind command-line interface.

Chunk 8 surface: `inboxmind connect` and `inboxmind sync`. Later chunks add
brief, review, and draft. Both commands are read-only against the mailbox;
connect requires an explicit human yes before any sign-in.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from postgrest import APIError
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.ingestion.graph_auth import MicrosoftGraphOAuthSettings
from src.ingestion.graph_token_cache import (
    ClientFactory,
    DeviceCodePrompt,
    EncryptedTokenCache,
    GraphAuthenticator,
    GraphAuthError,
    build_msal_client,
)
from src.ingestion.graph_transport import GraphTransportError, HttpxGraphTransport
from src.memory.supabase_client import SupabaseSettings, TableGateway, build_table_gateway
from src.models.auth_models import OAuthConsentRecord
from src.models.email_models import Provider
from src.sync_service import SyncReport, run_sync
from src.utils.encryption import FieldEncryptor

TOKEN_CACHE_FILENAME = "graph_token_cache.enc"  # noqa: S105 - filename, not a secret
CONSENT_LOG_FILENAME = "consent_log.jsonl"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG_ERROR = 2


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    encryption_key_base64: str = Field(min_length=1)
    inboxmind_home: Path = Field(default_factory=lambda: Path.home() / ".inboxmind")


class SyncTransport(Protocol):
    def get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]: ...

    def close(self) -> None: ...


GatewayFactory = Callable[[SupabaseSettings], TableGateway]
TransportFactory = Callable[[], SyncTransport]


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ClientFactory = build_msal_client,
    gateway_factory: GatewayFactory = build_table_gateway,
    transport_factory: TransportFactory = HttpxGraphTransport,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "connect":
        return _run_connect(client_factory)
    if args.command == "sync":
        return _run_sync(client_factory, gateway_factory, transport_factory)
    parser.error(f"unknown command: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inboxmind",
        description="Human-approved email and calendar intelligence.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "connect",
        help="Sign in to Microsoft Graph with read-only scopes via device-code flow.",
    )
    subparsers.add_parser(
        "sync",
        help="Pull mailbox changes through delta sync into encrypted Supabase storage.",
    )
    return parser


def _run_connect(client_factory: ClientFactory) -> int:
    app_settings = _load_settings(AppSettings, env_prefix="")
    if app_settings is None:
        return EXIT_CONFIG_ERROR
    graph_settings = _load_settings(MicrosoftGraphOAuthSettings, env_prefix="MICROSOFT_")
    if graph_settings is None:
        return EXIT_CONFIG_ERROR
    encryptor = _build_encryptor(app_settings)
    if encryptor is None:
        return EXIT_CONFIG_ERROR

    print("InboxMind will connect to Microsoft Graph with READ-ONLY scopes:")
    for scope in graph_settings.scopes:
        print(f"  - {scope}")
    print(f"Tenant: {graph_settings.tenant_id}")
    print("No mail is sent, moved, or modified. Tokens are cached encrypted at rest.")
    answer = input("Proceed with sign-in? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        print("Aborted; nothing was connected.")
        return EXIT_FAILURE

    cache_store = EncryptedTokenCache(app_settings.inboxmind_home / TOKEN_CACHE_FILENAME, encryptor)
    authenticator = GraphAuthenticator(graph_settings, cache_store, client_factory)
    try:
        token = authenticator.acquire_token(_print_device_prompt)
    except GraphAuthError as exc:
        print(f"Connection failed: {exc}")
        return EXIT_FAILURE

    record = OAuthConsentRecord(
        provider=Provider.MICROSOFT_GRAPH,
        account_id=token.account_id,
        subject=token.subject,
        scopes=list(token.scopes),
        granted_at=datetime.now(tz=UTC),
        tenant_id=token.tenant_id,
        account_type=token.account_type,
    )
    consent_path = app_settings.inboxmind_home / CONSENT_LOG_FILENAME
    _append_consent_record(consent_path, record)

    source = "cached token" if token.from_cache else "device-code sign-in"
    account_type = token.account_type or "unknown account type"
    print(f"Connected as {token.subject} ({account_type}) via {source}.")
    print(f"Consent recorded at {consent_path}.")
    return EXIT_OK


def _run_sync(
    client_factory: ClientFactory,
    gateway_factory: GatewayFactory,
    transport_factory: TransportFactory,
) -> int:
    app_settings = _load_settings(AppSettings, env_prefix="")
    if app_settings is None:
        return EXIT_CONFIG_ERROR
    graph_settings = _load_settings(MicrosoftGraphOAuthSettings, env_prefix="MICROSOFT_")
    if graph_settings is None:
        return EXIT_CONFIG_ERROR
    supabase_settings = _load_settings(SupabaseSettings, env_prefix="SUPABASE_")
    if supabase_settings is None:
        return EXIT_CONFIG_ERROR
    encryptor = _build_encryptor(app_settings)
    if encryptor is None:
        return EXIT_CONFIG_ERROR

    cache_store = EncryptedTokenCache(app_settings.inboxmind_home / TOKEN_CACHE_FILENAME, encryptor)
    authenticator = GraphAuthenticator(graph_settings, cache_store, client_factory)
    token = authenticator.acquire_cached_token()
    if token is None:
        print("No cached sign-in found. Run `inboxmind connect` first.")
        return EXIT_FAILURE

    consent_records = _read_consent_records(app_settings.inboxmind_home / CONSENT_LOG_FILENAME)
    gateway = gateway_factory(supabase_settings)
    transport = transport_factory()
    try:
        report = run_sync(
            token=token,
            transport=transport,
            gateway=gateway,
            encryptor=encryptor,
            consent_records=consent_records,
        )
    except GraphAuthError as exc:
        print(f"Sync failed: {exc}")
        return EXIT_FAILURE
    except GraphTransportError as exc:
        print(f"Sync failed after retries: {exc}")
        return EXIT_FAILURE
    except APIError as exc:
        print(f"Sync failed writing to Supabase: {exc.message}")
        print("Check SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY and apply supabase/schema.sql.")
        return EXIT_FAILURE
    except httpx.HTTPError as exc:
        print(f"Sync failed reaching Supabase: {exc!r}")
        return EXIT_FAILURE
    finally:
        transport.close()
    _print_sync_report(report)
    return EXIT_OK


def _print_sync_report(report: SyncReport) -> None:
    if report.resynced:
        mode = "resync after stale delta state"
    elif report.full_sync:
        mode = "full sync"
    else:
        mode = "incremental sync"
    print(f"Synced {report.account_email} ({report.mail_folder_id}, {mode}).")
    print(
        f"  {report.fetched} fetched, {report.inserted} stored encrypted, "
        f"{report.skipped_duplicates} duplicates skipped, "
        f"{report.deleted_upstream} deleted upstream."
    )
    print(f"  Consents uploaded: {report.consents_uploaded}. Delta checkpoint saved.")


def _print_device_prompt(prompt: DeviceCodePrompt) -> None:
    print(prompt.message)


def _load_settings[S: BaseSettings](settings_cls: type[S], *, env_prefix: str) -> S | None:
    try:
        return settings_cls()
    except ValidationError as exc:
        _print_settings_errors(exc, env_prefix=env_prefix)
        return None


def _build_encryptor(app_settings: AppSettings) -> FieldEncryptor | None:
    try:
        return FieldEncryptor(app_settings.encryption_key_base64.encode("utf-8"))
    except ValueError:
        print("Configuration error: ENCRYPTION_KEY_BASE64 is not a valid Fernet key.")
        print(
            "Generate one with: uv run python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
        return None


def _print_settings_errors(exc: ValidationError, *, env_prefix: str) -> None:
    print("Configuration error: missing or invalid environment settings.")
    for error in exc.errors():
        location = error["loc"]
        field = str(location[0]) if location else "unknown"
        print(f"  - {env_prefix}{field.upper()}: {error['msg']}")


def _read_consent_records(path: Path) -> list[OAuthConsentRecord]:
    if not path.exists():
        return []
    records: list[OAuthConsentRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            records.append(OAuthConsentRecord.model_validate_json(stripped))
    return records


def _append_consent_record(path: Path, record: OAuthConsentRecord) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json() + "\n")
