"""InboxMind command-line interface.

Chunk 7 surface: `inboxmind connect`. Later chunks add sync, brief, review,
and draft. Connecting is read-only and requires an explicit human yes.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

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
from src.models.auth_models import OAuthConsentRecord
from src.models.email_models import Provider
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


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ClientFactory = build_msal_client,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "connect":
        return _run_connect(client_factory)
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
    return parser


def _run_connect(client_factory: ClientFactory) -> int:
    try:
        app_settings = AppSettings()
    except ValidationError as exc:
        _print_settings_errors(exc, env_prefix="")
        return EXIT_CONFIG_ERROR
    try:
        graph_settings = MicrosoftGraphOAuthSettings()
    except ValidationError as exc:
        _print_settings_errors(exc, env_prefix="MICROSOFT_")
        return EXIT_CONFIG_ERROR
    try:
        encryptor = FieldEncryptor(app_settings.encryption_key_base64.encode("utf-8"))
    except ValueError:
        print("Configuration error: ENCRYPTION_KEY_BASE64 is not a valid Fernet key.")
        print(
            "Generate one with: uv run python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
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


def _print_device_prompt(prompt: DeviceCodePrompt) -> None:
    print(prompt.message)


def _print_settings_errors(exc: ValidationError, *, env_prefix: str) -> None:
    print("Configuration error: missing or invalid environment settings.")
    for error in exc.errors():
        location = error["loc"]
        field = str(location[0]) if location else "unknown"
        print(f"  - {env_prefix}{field.upper()}: {error['msg']}")


def _append_consent_record(path: Path, record: OAuthConsentRecord) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json() + "\n")
