"""Bootstrap the account row chain and upload consent records.

`emails`, `threads`, `account_consents`, and `account_sync_checkpoints` all
foreign-key to `accounts.id`, and `accounts` requires a persona, so the first
sync creates the minimal chain. The default persona row exists only to satisfy
that constraint until chunk 9 loads real personas from YAML.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.memory.supabase_client import SupabaseStoreError, TableGateway
from src.models.auth_models import OAuthConsentRecord
from src.models.email_models import Provider

PERSONAS_TABLE = "personas"
ACCOUNTS_TABLE = "accounts"
CONSENTS_TABLE = "account_consents"
DEFAULT_PROFILE_ID = "default"


def ensure_account(
    gateway: TableGateway,
    *,
    provider: Provider,
    primary_email: str,
    display_name: str,
    org_type: str,
    scopes: list[str],
) -> str:
    """Return the `accounts.id` for this mailbox, creating persona and account rows once."""
    rows = gateway.select_rows(
        ACCOUNTS_TABLE,
        "id",
        eq={"provider": provider.value, "primary_email": primary_email},
    )
    account_id = _single_id(rows)
    if account_id is not None:
        return account_id
    persona_id = _ensure_default_persona(gateway)
    inserted = gateway.insert_rows(
        ACCOUNTS_TABLE,
        [
            {
                "persona_id": persona_id,
                "provider": provider.value,
                "primary_email": primary_email,
                "display_name": display_name,
                "org_type": org_type,
                "scopes": scopes,
                "consent_logged_at": datetime.now(tz=UTC).isoformat(),
            }
        ],
    )
    account_id = _single_id(inserted)
    if account_id is None:
        msg = f"Supabase did not return an id for the new {ACCOUNTS_TABLE} row"
        raise SupabaseStoreError(msg)
    return account_id


def upload_consents(
    gateway: TableGateway, *, account_id: str, records: list[OAuthConsentRecord]
) -> int:
    """Insert consent records not yet in `account_consents`; return how many were uploaded."""
    if not records:
        return 0
    existing = gateway.select_rows(
        CONSENTS_TABLE, "subject,granted_at", eq={"account_id": account_id}
    )
    seen = {
        (str(row.get("subject")), _canonical_instant(str(row.get("granted_at"))))
        for row in existing
    }
    payloads: list[dict[str, Any]] = []
    for record in records:
        key = (record.subject, record.granted_at.astimezone(UTC).isoformat())
        if key in seen:
            continue
        seen.add(key)
        payloads.append(
            {
                "account_id": account_id,
                "provider": record.provider.value,
                "subject": record.subject,
                "tenant_id": record.tenant_id,
                "scopes": record.scopes,
                "human_confirmed": record.human_confirmed,
                "granted_at": record.granted_at.astimezone(UTC).isoformat(),
            }
        )
    gateway.insert_rows(CONSENTS_TABLE, payloads)
    return len(payloads)


def _ensure_default_persona(gateway: TableGateway) -> str:
    rows = gateway.select_rows(PERSONAS_TABLE, "id", eq={"profile_id": DEFAULT_PROFILE_ID})
    persona_id = _single_id(rows)
    if persona_id is not None:
        return persona_id
    inserted = gateway.insert_rows(
        PERSONAS_TABLE,
        [
            {
                "profile_id": DEFAULT_PROFILE_ID,
                "display_name": "Default",
                "tone": "neutral",
                "filing_taxonomy": "general",
                "response_constraints": [],
            }
        ],
    )
    persona_id = _single_id(inserted)
    if persona_id is None:
        msg = f"Supabase did not return an id for the new {PERSONAS_TABLE} row"
        raise SupabaseStoreError(msg)
    return persona_id


def _single_id(rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None
    identifier = rows[0].get("id")
    return str(identifier) if identifier is not None else None


def _canonical_instant(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(UTC).isoformat()
    except ValueError:
        return value
