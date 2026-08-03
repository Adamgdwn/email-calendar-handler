"""InboxMind command-line interface.

Chunk 15 surface: all commands from chunks 7-14 plus multi-account support.
`connect --account <alias>` and `sync --account <alias>` target a specific
account; `sync` with no alias iterates all accounts listed in INBOXMIND_ACCOUNTS.
`brief` renders all accounts in one brief, each with its own persona tone.
Every command is read-only against the mailbox; connect requires an explicit
human yes before any sign-in; draft and audit output is never written to the
mailbox.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from cryptography.fernet import InvalidToken
from postgrest import APIError
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.agents.llm_classification_assist import (
    LLM_ASSIST_DAILY_BUDGET_DEFAULT,
    LLM_ASSIST_THRESHOLD_DEFAULT,
    LLMAssistConfig,
)
from src.agents.response_agent import ResponseAgent
from src.brief.renderer import render_multi_brief
from src.brief_service import (
    ACCOUNT_COLUMNS,
    DEFAULT_LOOKBACK_HOURS,
    BriefDataError,
    PersonaSelectionError,
    run_multi_brief,
)
from src.inbox_audit.audit_renderer import render_audit_report
from src.inbox_audit.audit_synthesizer import AuditSynthesisError, AuditSynthesizer
from src.inbox_audit.cluster_builder import ClusterBuilder
from src.inbox_audit.folder_fetcher import AuditFetchError, FolderFetcher
from src.ingestion.graph_auth import MicrosoftGraphOAuthSettings
from src.ingestion.graph_calendar import GraphCalendarError
from src.ingestion.graph_token_cache import (
    ClientFactory,
    DeviceCodePrompt,
    EncryptedTokenCache,
    GraphAuthenticator,
    GraphAuthError,
    build_msal_client,
)
from src.ingestion.graph_transport import GraphTransportError, HttpxGraphTransport
from src.llm.anthropic_client import AnthropicClient
from src.memory.account_store import ACCOUNTS_TABLE, link_account_persona, persona_profile_id
from src.memory.email_store import EMAILS_TABLE
from src.memory.supabase_client import SupabaseSettings, TableGateway, build_table_gateway
from src.models.audit_models import AuditReport
from src.models.auth_models import OAuthConsentRecord
from src.models.brief_models import FilingProposal
from src.models.email_models import Provider
from src.models.feedback_models import FeedbackDecision
from src.models.persona_models import DraftRequest, DraftResponse, ThreadMessage
from src.personas.loader import PersonaLoadError, load_personas
from src.review_service import ReviewInput, ReviewReport, run_review
from src.sync_service import DEFAULT_CALENDAR_DAYS, SyncReport, run_sync
from src.utils.encryption import FieldEncryptor

TOKEN_CACHE_FILENAME = "graph_token_cache.enc"  # noqa: S105 - filename, not a secret
CONSENT_LOG_FILENAME = "consent_log.jsonl"


def _token_cache_filename(alias: str | None) -> str:
    """Return the encrypted token cache filename for the given account alias.

    No alias → backward-compatible single-account filename.
    With alias → account-scoped name so multiple accounts coexist.
    """
    if alias:
        return f"graph_token_cache_{alias}.enc"  # noqa: S105 - filename, not a secret
    return TOKEN_CACHE_FILENAME


DRAFT_THREAD_COLUMNS = "id,thread_id,sender_email,subject,body_ciphertext,message_timestamp"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG_ERROR = 2


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    encryption_key_base64: str = Field(min_length=1)
    inboxmind_home: Path = Field(default_factory=lambda: Path.home() / ".inboxmind")


class AnthropicSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_", env_file=".env", extra="ignore")

    api_key: str = Field(min_length=1)


class LLMAssistSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_ASSIST_", env_file=".env", extra="ignore")

    enabled: bool = Field(default=False)
    confidence_threshold: float = Field(default=LLM_ASSIST_THRESHOLD_DEFAULT, ge=0.0, le=1.0)
    daily_token_budget: int = Field(default=LLM_ASSIST_DAILY_BUDGET_DEFAULT, ge=0)


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
        return _run_connect(client_factory, account_alias=args.account_alias)
    if args.command == "sync":
        return _run_sync(
            client_factory,
            gateway_factory,
            transport_factory,
            account_alias=args.account_alias,
            calendar_days=args.calendar_days,
        )
    if args.command == "brief":
        return _run_brief(gateway_factory, profile=args.profile, hours=args.hours)
    if args.command == "review":
        return _run_review(gateway_factory, profile=args.profile, hours=args.hours)
    if args.command == "draft":
        return _run_draft(
            gateway_factory,
            thread_id=args.thread_id,
            profile=args.profile,
            hours=args.hours,
        )
    if args.command == "audit":
        return _run_audit(client_factory, transport_factory, months=args.months)
    parser.error(f"unknown command: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inboxmind",
        description="Human-approved email and calendar intelligence.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    connect_parser = subparsers.add_parser(
        "connect",
        help="Sign in to Microsoft Graph with read-only scopes via device-code flow.",
    )
    connect_parser.add_argument(
        "--account",
        dest="account_alias",
        default=None,
        metavar="ALIAS",
        help="Account alias for multi-account setups (e.g. guided_ai_labs). "
        "Uses a dedicated token cache when given.",
    )
    sync_parser = subparsers.add_parser(
        "sync",
        help="Pull mailbox changes and a calendar window into encrypted Supabase storage.",
    )
    sync_parser.add_argument(
        "--account",
        dest="account_alias",
        default=None,
        metavar="ALIAS",
        help="Sync a specific account alias. Omit to sync all accounts in INBOXMIND_ACCOUNTS.",
    )
    sync_parser.add_argument(
        "--calendar-days",
        type=int,
        default=DEFAULT_CALENDAR_DAYS,
        help=f"Fetch events for today +/- N days (default {DEFAULT_CALENDAR_DAYS}, minimum 1).",
    )
    brief_parser = subparsers.add_parser(
        "brief",
        help="Render the Morning Brief from synced mail (terminal + brief-YYYY-MM-DD.md).",
    )
    brief_parser.add_argument(
        "--profile",
        help="Persona profile for classification; updates the account's stored persona.",
    )
    brief_parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help=f"Lookback window in hours (default {DEFAULT_LOOKBACK_HOURS}).",
    )
    review_parser = subparsers.add_parser(
        "review",
        help="Accept/modify/reject filing proposals; feedback trains the LearningAgent.",
    )
    review_parser.add_argument(
        "--profile",
        help="Persona profile for classification; updates the account's stored persona.",
    )
    review_parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help=f"Lookback window in hours (default {DEFAULT_LOOKBACK_HOURS}).",
    )
    draft_parser = subparsers.add_parser(
        "draft",
        help="Generate a persona-toned reply draft for terminal review only; nothing is sent.",
    )
    draft_parser.add_argument(
        "thread_id",
        nargs="?",
        default=None,
        help="Internal thread UUID from `inboxmind brief`. Omit to pick from a menu.",
    )
    draft_parser.add_argument(
        "--profile",
        help="Persona profile for tone; uses the account's linked persona if omitted.",
    )
    draft_parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help=f"Lookback window for the thread menu (default {DEFAULT_LOOKBACK_HOURS}).",
    )
    audit_parser = subparsers.add_parser(
        "audit",
        help=(
            "Scan folder tree and propose a better filing hierarchy; "
            "writes a report to INBOXMIND_HOME/audits/."
        ),
    )
    audit_parser.add_argument(
        "--months",
        type=int,
        default=12,
        help="Scan messages from the last N months (default 12).",
    )
    return parser


def _run_connect(client_factory: ClientFactory, *, account_alias: str | None = None) -> int:
    app_settings = _load_settings(AppSettings, env_prefix="")
    if app_settings is None:
        return EXIT_CONFIG_ERROR
    graph_settings = _load_settings(MicrosoftGraphOAuthSettings, env_prefix="MICROSOFT_")
    if graph_settings is None:
        return EXIT_CONFIG_ERROR
    encryptor = _build_encryptor(app_settings)
    if encryptor is None:
        return EXIT_CONFIG_ERROR

    alias_label = f" [{account_alias}]" if account_alias else ""
    print(f"InboxMind{alias_label} will connect to Microsoft Graph with READ-ONLY scopes:")
    for scope in graph_settings.scopes:
        print(f"  - {scope}")
    print(f"Tenant: {graph_settings.tenant_id}")
    print("No mail is sent, moved, or modified. Tokens are cached encrypted at rest.")
    answer = input("Proceed with sign-in? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        print("Aborted; nothing was connected.")
        return EXIT_FAILURE

    cache_store = EncryptedTokenCache(
        app_settings.inboxmind_home / _token_cache_filename(account_alias), encryptor
    )
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
    *,
    account_alias: str | None = None,
    calendar_days: int,
) -> int:
    if calendar_days < 1:
        print("Configuration error: --calendar-days must be at least 1.")
        return EXIT_CONFIG_ERROR
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

    # Determine which account aliases to sync
    if account_alias:
        aliases: list[str | None] = [account_alias]
    else:
        raw = os.environ.get("INBOXMIND_ACCOUNTS", "").strip()
        aliases = [a.strip() for a in raw.split(",") if a.strip()] if raw else [None]

    overall = EXIT_OK
    for alias in aliases:
        result = _sync_alias(
            alias,
            client_factory=client_factory,
            gateway_factory=gateway_factory,
            transport_factory=transport_factory,
            app_settings=app_settings,
            graph_settings=graph_settings,
            supabase_settings=supabase_settings,
            encryptor=encryptor,
            calendar_days=calendar_days,
        )
        if result != EXIT_OK:
            overall = result
    return overall


def _sync_alias(
    alias: str | None,
    *,
    client_factory: ClientFactory,
    gateway_factory: GatewayFactory,
    transport_factory: TransportFactory,
    app_settings: AppSettings,
    graph_settings: MicrosoftGraphOAuthSettings,
    supabase_settings: SupabaseSettings,
    encryptor: FieldEncryptor,
    calendar_days: int,
) -> int:
    cache_store = EncryptedTokenCache(
        app_settings.inboxmind_home / _token_cache_filename(alias), encryptor
    )
    authenticator = GraphAuthenticator(graph_settings, cache_store, client_factory)
    token = authenticator.acquire_cached_token()
    if token is None:
        alias_hint = f" --account {alias}" if alias else ""
        print(f"No cached sign-in found. Run `inboxmind connect{alias_hint}` first.")
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
            calendar_days=calendar_days,
        )
    except GraphAuthError as exc:
        print(f"Sync failed: {exc}")
        return EXIT_FAILURE
    except GraphTransportError as exc:
        print(f"Sync failed after retries: {exc}")
        return EXIT_FAILURE
    except GraphCalendarError as exc:
        print(f"Calendar sync failed: {exc}")
        print("Mail progress was already checkpointed; re-run `inboxmind sync` once fixed.")
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


def _prompt_profile(choices: list[str]) -> str | None:
    """Interactively pick a persona profile; returns None if input is invalid or non-interactive."""
    print("\nFirst run: no persona profile linked yet. Choose one:")
    for i, name in enumerate(choices, 1):
        print(f"  {i}) {name}")
    try:
        raw = input("Enter number or name: ").strip().lower()
    except EOFError:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(choices):
        return choices[int(raw) - 1]
    if raw in choices:
        return raw
    print(f"Invalid choice: {raw!r}.")
    return None


def _run_brief(gateway_factory: GatewayFactory, *, profile: str | None, hours: int) -> int:
    if hours < 1:
        print("Configuration error: --hours must be at least 1.")
        return EXIT_CONFIG_ERROR
    app_settings = _load_settings(AppSettings, env_prefix="")
    if app_settings is None:
        return EXIT_CONFIG_ERROR
    supabase_settings = _load_settings(SupabaseSettings, env_prefix="SUPABASE_")
    if supabase_settings is None:
        return EXIT_CONFIG_ERROR
    encryptor = _build_encryptor(app_settings)
    if encryptor is None:
        return EXIT_CONFIG_ERROR
    try:
        personas = load_personas()
    except PersonaLoadError as exc:
        print(f"Configuration error: {exc}")
        return EXIT_CONFIG_ERROR

    llm_assist_config: LLMAssistConfig | None = None
    llm_assist_settings = _load_settings(LLMAssistSettings, env_prefix="LLM_ASSIST_")
    if llm_assist_settings is not None and llm_assist_settings.enabled:
        anthropic_settings = _load_settings(AnthropicSettings, env_prefix="ANTHROPIC_")
        if anthropic_settings is None:
            print(
                "LLM_ASSIST_ENABLED=true but ANTHROPIC_API_KEY missing; running without LLM assist."
            )
        else:
            llm_assist_config = LLMAssistConfig(
                confidence_threshold=llm_assist_settings.confidence_threshold,
                daily_token_budget=llm_assist_settings.daily_token_budget,
                api_key=anthropic_settings.api_key,
                budget_path=app_settings.inboxmind_home / "llm_assist_budget.json",
            )

    gateway = gateway_factory(supabase_settings)
    _profile = profile
    try:
        multi_brief = run_multi_brief(
            gateway=gateway,
            encryptor=encryptor,
            personas=personas,
            profile_override=_profile,
            lookback_hours=hours,
            llm_assist_config=llm_assist_config,
        )
    except PersonaSelectionError as exc:
        if _profile is not None:
            print(f"Configuration error: {exc}")
            return EXIT_CONFIG_ERROR
        # No profile linked yet — prompt and retry once.
        _profile = _prompt_profile(sorted(personas))
        if _profile is None:
            return EXIT_CONFIG_ERROR
        try:
            multi_brief = run_multi_brief(
                gateway=gateway,
                encryptor=encryptor,
                personas=personas,
                profile_override=_profile,
                lookback_hours=hours,
                llm_assist_config=llm_assist_config,
            )
        except PersonaSelectionError as exc2:
            print(f"Configuration error: {exc2}")
            return EXIT_CONFIG_ERROR
        except BriefDataError as exc2:
            print(f"Brief failed: {exc2}")
            return EXIT_FAILURE
        except APIError as exc2:
            print(f"Brief failed reading Supabase: {exc2.message}")
            print("Check SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY and apply supabase/schema.sql.")
            return EXIT_FAILURE
        except httpx.HTTPError as exc2:
            print(f"Brief failed reaching Supabase: {exc2!r}")
            return EXIT_FAILURE
    except BriefDataError as exc:
        print(f"Brief failed: {exc}")
        return EXIT_FAILURE
    except APIError as exc:
        print(f"Brief failed reading Supabase: {exc.message}")
        print("Check SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY and apply supabase/schema.sql.")
        return EXIT_FAILURE
    except httpx.HTTPError as exc:
        print(f"Brief failed reaching Supabase: {exc!r}")
        return EXIT_FAILURE
    markdown = render_multi_brief(multi_brief)
    print(markdown)
    path = _write_brief_file(app_settings.inboxmind_home, multi_brief.brief_date, markdown)
    print(f"Brief written to {path}")
    return EXIT_OK


class StdinReviewPrompter:
    """Interactive filing-decision prompt at the terminal; the CLI's I/O boundary."""

    def review(self, proposal: FilingProposal) -> ReviewInput:
        path = "/".join(proposal.proposed_path)
        print(f"\n  ── {proposal.urgency.value.upper()} ──────────────────────────────")
        print(f"  Thread:  {proposal.subject}")
        print(f"  File under:  {path}")
        print()
        print("  a = Yes, file it there   (InboxMind learns this folder fits)")
        print("  m = No, use a different folder  (you type the path; it learns that instead)")
        print("  r = Don't file this      (InboxMind learns no folder fits)")
        print("  s = Skip                 (no feedback recorded, asked again next run)")
        answer = input("\n  Choice [a/m/r/s]: ").strip().lower()
        if answer in {"a", "accept"}:
            return ReviewInput(decision=FeedbackDecision.ACCEPT)
        if answer in {"m", "modify"}:
            raw = input("  Folder path (slash-separated, e.g. Clients/Acme): ").strip()
            parts = [segment.strip() for segment in raw.split("/") if segment.strip()]
            return ReviewInput(decision=FeedbackDecision.MODIFY, modified_path=parts or None)
        if answer in {"r", "reject"}:
            return ReviewInput(decision=FeedbackDecision.REJECT)
        return ReviewInput()


def _run_review(gateway_factory: GatewayFactory, *, profile: str | None, hours: int) -> int:
    if hours < 1:
        print("Configuration error: --hours must be at least 1.")
        return EXIT_CONFIG_ERROR
    app_settings = _load_settings(AppSettings, env_prefix="")
    if app_settings is None:
        return EXIT_CONFIG_ERROR
    supabase_settings = _load_settings(SupabaseSettings, env_prefix="SUPABASE_")
    if supabase_settings is None:
        return EXIT_CONFIG_ERROR
    encryptor = _build_encryptor(app_settings)
    if encryptor is None:
        return EXIT_CONFIG_ERROR
    try:
        personas = load_personas()
    except PersonaLoadError as exc:
        print(f"Configuration error: {exc}")
        return EXIT_CONFIG_ERROR

    gateway = gateway_factory(supabase_settings)
    try:
        report = run_review(
            gateway=gateway,
            encryptor=encryptor,
            personas=personas,
            prompter=StdinReviewPrompter(),
            profile_override=profile,
            lookback_hours=hours,
        )
    except PersonaSelectionError as exc:
        print(f"Configuration error: {exc}")
        return EXIT_CONFIG_ERROR
    except BriefDataError as exc:
        print(f"Review failed: {exc}")
        return EXIT_FAILURE
    except APIError as exc:
        print(f"Review failed reading Supabase: {exc.message}")
        print("Check SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY and apply supabase/schema.sql.")
        return EXIT_FAILURE
    except httpx.HTTPError as exc:
        print(f"Review failed reaching Supabase: {exc!r}")
        return EXIT_FAILURE
    _print_review_report(report)
    return EXIT_OK


def _run_draft(
    gateway_factory: GatewayFactory,
    *,
    thread_id: str | None,
    profile: str | None,
    hours: int,
) -> int:
    if hours < 1:
        print("Configuration error: --hours must be at least 1.")
        return EXIT_CONFIG_ERROR
    app_settings = _load_settings(AppSettings, env_prefix="")
    if app_settings is None:
        return EXIT_CONFIG_ERROR
    supabase_settings = _load_settings(SupabaseSettings, env_prefix="SUPABASE_")
    if supabase_settings is None:
        return EXIT_CONFIG_ERROR
    anthropic_settings = _load_settings(AnthropicSettings, env_prefix="ANTHROPIC_")
    if anthropic_settings is None:
        return EXIT_CONFIG_ERROR
    encryptor = _build_encryptor(app_settings)
    if encryptor is None:
        return EXIT_CONFIG_ERROR
    try:
        personas = load_personas()
    except PersonaLoadError as exc:
        print(f"Configuration error: {exc}")
        return EXIT_CONFIG_ERROR

    gateway = gateway_factory(supabase_settings)

    account_rows = gateway.select_rows(ACCOUNTS_TABLE, ACCOUNT_COLUMNS, eq={})
    if not account_rows:
        print("No synced account found. Run `inboxmind connect` then `inboxmind sync` first.")
        return EXIT_FAILURE
    account = account_rows[0]
    account_id = str(account["id"])

    profile_id_stored = persona_profile_id(gateway, persona_row_id=str(account.get("persona_id")))
    profile_to_use = profile or profile_id_stored
    if profile_to_use is None:
        profile_to_use = _prompt_profile(sorted(personas))
        if profile_to_use is None:
            return EXIT_CONFIG_ERROR
    persona = personas.get(profile_to_use)
    if persona is None:
        available = ", ".join(sorted(personas))
        print(f"Configuration error: Unknown profile '{profile_to_use}'. Available: {available}.")
        return EXIT_CONFIG_ERROR
    if profile is not None:
        link_account_persona(gateway, account_id=account_id, persona=persona)

    if thread_id is None:
        thread_id = _pick_draft_thread(gateway, account_id, hours=hours)
        if thread_id is None:
            return EXIT_FAILURE

    thread_rows = gateway.select_rows(
        EMAILS_TABLE,
        DRAFT_THREAD_COLUMNS,
        eq={"account_id": account_id, "thread_id": thread_id},
    )
    if not thread_rows:
        print(f"Thread '{thread_id}' not found. Run `inboxmind brief` to see thread IDs.")
        return EXIT_FAILURE

    thread_rows.sort(key=lambda r: str(r.get("message_timestamp", "")))
    thread_messages: list[ThreadMessage] = []
    for row in thread_rows:
        try:
            body_text = encryptor.decrypt_text(str(row.get("body_ciphertext", "")))
        except (InvalidToken, ValueError):
            body_text = "(body unavailable)"
        ts_raw = str(row.get("message_timestamp") or datetime.now(UTC).isoformat())
        thread_messages.append(
            ThreadMessage(
                sender_email=str(row.get("sender_email", "")),
                subject=str(row.get("subject", "")),
                body_text=body_text,
                received_at=datetime.fromisoformat(ts_raw),
            )
        )

    agent = ResponseAgent(AnthropicClient(anthropic_settings.api_key))
    request = DraftRequest(
        account_id=account_id,
        thread_id=thread_id,
        persona=persona,
        thread_messages=thread_messages,
    )
    draft = agent.run(request)
    _print_draft(draft)
    return EXIT_OK


def _run_audit(
    client_factory: ClientFactory,
    transport_factory: TransportFactory,
    *,
    months: int,
) -> int:
    from datetime import timedelta

    from src.ingestion.graph_auth import MicrosoftGraphOAuthSettings

    if months < 1:
        print("Configuration error: --months must be at least 1.")
        return EXIT_CONFIG_ERROR
    app_settings = _load_settings(AppSettings, env_prefix="")
    if app_settings is None:
        return EXIT_CONFIG_ERROR
    graph_settings = _load_settings(MicrosoftGraphOAuthSettings, env_prefix="MICROSOFT_")
    if graph_settings is None:
        return EXIT_CONFIG_ERROR
    anthropic_settings = _load_settings(AnthropicSettings, env_prefix="ANTHROPIC_")
    if anthropic_settings is None:
        return EXIT_CONFIG_ERROR
    encryptor = _build_encryptor(app_settings)
    if encryptor is None:
        return EXIT_CONFIG_ERROR

    from src.ingestion.graph_token_cache import EncryptedTokenCache, GraphAuthenticator

    cache_store = EncryptedTokenCache(app_settings.inboxmind_home / TOKEN_CACHE_FILENAME, encryptor)
    authenticator = GraphAuthenticator(graph_settings, cache_store, client_factory)
    token = authenticator.acquire_cached_token()
    if token is None:
        print("No cached sign-in found. Run `inboxmind connect` first.")
        return EXIT_FAILURE

    access_token = token.access_token.get_secret_value()
    cutoff = (datetime.now(UTC) - timedelta(days=30 * months)).strftime("%Y-%m-%dT%H:%M:%SZ")

    transport = transport_factory()
    try:
        fetcher = FolderFetcher(transport, access_token)
        print(f"Fetching folder tree for {token.subject}…")
        folder_tree = fetcher.fetch_folder_tree()

        all_rows = []
        flat_folders = _collect_folder_paths(folder_tree)
        for folder_node, folder_path in flat_folders:
            rows = fetcher.fetch_message_metadata(folder_node.folder_id, folder_path, cutoff)
            all_rows.extend(rows)
        print(f"  {len(all_rows):,} message metadata rows across {len(flat_folders)} folders.")

        summary = ClusterBuilder().build(
            rows=all_rows,
            folder_tree=folder_tree,
            account_email=token.subject,
            months_scanned=months,
        )

        print("Synthesizing folder proposal with Anthropic…")
        synthesizer = AuditSynthesizer(AnthropicClient(anthropic_settings.api_key))
        try:
            proposal, llm_response = synthesizer.synthesize(summary)
        except AuditSynthesisError as exc:
            print(f"Audit synthesis failed: {exc}")
            return EXIT_FAILURE

        audits_dir = app_settings.inboxmind_home / "audits"
        report_path = audits_dir / f"audit-{date.today().isoformat()}.md"
        report = AuditReport(
            summary=summary,
            proposal=proposal,
            report_path=report_path,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
        )
        render_audit_report(report)
    except AuditFetchError as exc:
        print(f"Audit fetch failed: {exc}")
        return EXIT_FAILURE
    except GraphTransportError as exc:
        print(f"Audit fetch failed after retries: {exc}")
        return EXIT_FAILURE
    finally:
        transport.close()
    return EXIT_OK


def _collect_folder_paths(
    nodes: list[Any], prefix: list[str] | None = None
) -> list[tuple[Any, list[str]]]:
    """Flatten a folder tree into (FolderNode, path) pairs, depth-first."""
    prefix = prefix or []
    result: list[tuple[Any, list[str]]] = []
    for node in nodes:
        path = [*prefix, node.display_name]
        result.append((node, path))
        result.extend(_collect_folder_paths(node.child_folders, path))
    return result


def _pick_draft_thread(gateway: TableGateway, account_id: str, *, hours: int) -> str | None:
    from datetime import timedelta

    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    rows = gateway.select_rows(
        EMAILS_TABLE,
        "id,thread_id,sender_email,subject,message_timestamp",
        eq={"account_id": account_id},
        gte=("message_timestamp", cutoff),
    )
    if not rows:
        print(f"No mail in the last {hours} hour(s). Try a wider window with --hours.")
        return None
    by_thread: dict[str, dict[str, Any]] = {}
    for row in rows:
        tid = str(row.get("thread_id"))
        ts = str(row.get("message_timestamp", ""))
        if tid not in by_thread or ts > str(by_thread[tid].get("message_timestamp", "")):
            by_thread[tid] = row
    threads = sorted(
        by_thread.values(), key=lambda r: str(r.get("message_timestamp", "")), reverse=True
    )
    print("\nRecent threads — pick one to draft a reply:")
    for i, row in enumerate(threads, 1):
        ts = str(row.get("message_timestamp", ""))[:16].replace("T", " ")
        print(f"  {i}) {row.get('subject')} · {row.get('sender_email')} · {ts}")
    try:
        raw = input("\n  Thread number: ").strip()
    except EOFError:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(threads):
        return str(threads[int(raw) - 1]["thread_id"])
    print(f"Invalid choice: {raw!r}.")
    return None


def _print_draft(draft: DraftResponse) -> None:
    print("\n  ── DRAFT (NOT APPROVED — for review only; nothing is sent) ──")
    print(f"  Subject: {draft.subject_recommendation}")
    print(f"  Send timing: {draft.suggested_send_timing}")
    print()
    print(draft.body)
    print(
        f"\n  ── {draft.input_tokens} tokens in · {draft.output_tokens} tokens out"
        " · edit distance: pending review ──"
    )


def _print_review_report(report: ReviewReport) -> None:
    print(f"\nReviewed {report.reviewed} proposal(s) for {report.account_email}:")
    print(f"  {report.accepted} accepted, {report.modified} modified, {report.rejected} rejected.")
    print(
        f"  {report.feedback_recorded} feedback record(s) saved; "
        f"{report.rules_written} filing rule(s) updated."
    )
    if report.promoted_paths:
        print(f"  Promoted to confirmed: {', '.join(report.promoted_paths)}.")
    if report.retired_paths:
        print(f"  Retired: {', '.join(report.retired_paths)}.")
    stats = report.acceptance
    if stats.total:
        print(f"  Filing acceptance: {stats.rate:.0%} ({stats.accepted}/{stats.total} reviewed).")


def _write_brief_file(home: Path, brief_date: date, markdown: str) -> Path:
    briefs_dir = home / "briefs"
    briefs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = briefs_dir / f"brief-{brief_date.isoformat()}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


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
    print(
        f"  Calendar: {report.calendar_events_stored} events stored "
        f"for today +/- {report.calendar_days} day(s)."
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
