"""Orchestrate the Morning Brief: classify synced mail, persist, summarize.

Reads only from Supabase; never touches the mailbox. Classification receives
metadata plus a bounded excerpt of the locally decrypted body - full bodies
never reach agents, matching the `ClassificationInput` excerpt contract.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.fernet import InvalidToken
from pydantic import ValidationError

from src.agents.supervisor import EmailSupervisor
from src.memory.account_store import ACCOUNTS_TABLE, link_account_persona, persona_profile_id
from src.memory.email_store import EMAILS_TABLE
from src.memory.rule_store import SupabaseRuleStore
from src.memory.supabase_client import TableGateway
from src.models.brief_models import URGENCY_ORDER, BriefThreadSummary, FilingProposal, MorningBrief
from src.models.email_models import (
    AccountContext,
    Classification,
    ClassificationInput,
    EmailAddress,
    Provider,
)
from src.models.filing_models import FilingRule
from src.models.persona_models import PersonaProfile
from src.utils.encryption import FieldEncryptor

DEFAULT_LOOKBACK_HOURS = 24
EXCERPT_CHARS = 500
ACCOUNT_COLUMNS = "id,persona_id,provider,primary_email,display_name,org_type,timezone"
EMAIL_COLUMNS = (
    "id,thread_id,subject,sender_email,body_ciphertext,message_timestamp,"
    "labels,urgency,classification"
)


class BriefDataError(RuntimeError):
    """Raised when stored state cannot produce a brief (no account, bad key)."""


class PersonaSelectionError(RuntimeError):
    """Raised when no YAML persona matches the account and none was chosen."""


def run_brief(
    *,
    gateway: TableGateway,
    encryptor: FieldEncryptor,
    personas: dict[str, PersonaProfile],
    profile_override: str | None = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    now: datetime | None = None,
) -> MorningBrief:
    moment = (now or datetime.now(tz=UTC)).astimezone(UTC)
    account = _load_single_account(gateway)
    account_id = str(account["id"])
    persona = _resolve_persona(gateway, account, personas, profile_override)
    account_zone = _account_zone(str(account.get("timezone") or "UTC"))
    cutoff = moment - timedelta(hours=lookback_hours)
    rows = gateway.select_rows(
        EMAILS_TABLE,
        EMAIL_COLUMNS,
        eq={"account_id": account_id},
        gte=("message_timestamp", cutoff.isoformat()),
    )
    supervisor = EmailSupervisor.default(persona)
    context = _account_context(account, persona.profile_id)
    classified: dict[str, Classification] = {}
    classified_now = 0
    previously_classified = 0
    for row in rows:
        email_id = str(row["id"])
        stored = _stored_classification(row)
        if stored is not None:
            classified[email_id] = stored
            previously_classified += 1
            continue
        classification = supervisor.classify(_classification_input(context, row, encryptor))
        _persist_classification(gateway, email_id, classification)
        classified[email_id] = classification
        classified_now += 1
    rules = SupabaseRuleStore(gateway).list_rules(account_id)
    proposals = _build_proposals(supervisor, account_id, rows, classified, rules)
    threads = _build_threads(rows, classified, persona.profile_id, account_zone)
    return MorningBrief(
        brief_date=moment.astimezone(account_zone).date(),
        account_email=str(account.get("primary_email")),
        profile_id=persona.profile_id,
        persona_display_name=persona.display_name,
        lookback_hours=lookback_hours,
        generated_at=moment.astimezone(account_zone),
        threads=threads,
        proposals=proposals,
        classified_now=classified_now,
        previously_classified=previously_classified,
    )


def _load_single_account(gateway: TableGateway) -> dict[str, Any]:
    rows = gateway.select_rows(ACCOUNTS_TABLE, ACCOUNT_COLUMNS, eq={})
    if not rows:
        msg = "No synced account found. Run `inboxmind connect` then `inboxmind sync` first."
        raise BriefDataError(msg)
    if len(rows) > 1:
        msg = "Multiple accounts found; the Morning Brief handles one account in this milestone."
        raise BriefDataError(msg)
    return rows[0]


def _resolve_persona(
    gateway: TableGateway,
    account: dict[str, Any],
    personas: dict[str, PersonaProfile],
    profile_override: str | None,
) -> PersonaProfile:
    choices = "|".join(sorted(personas))
    if profile_override is not None:
        persona = personas.get(profile_override)
        if persona is None:
            msg = f"Unknown profile '{profile_override}'. Available: {choices}."
            raise PersonaSelectionError(msg)
        link_account_persona(gateway, account_id=str(account["id"]), persona=persona)
        return persona
    profile_id = persona_profile_id(gateway, persona_row_id=str(account.get("persona_id")))
    if profile_id is not None and profile_id in personas:
        return personas[profile_id]
    msg = (
        f"Account persona '{profile_id or 'unknown'}' has no YAML definition. "
        f"Re-run with --profile <{choices}>."
    )
    raise PersonaSelectionError(msg)


def _account_context(account: dict[str, Any], profile_id: str) -> AccountContext:
    return AccountContext(
        account_id=str(account["id"]),
        profile_id=profile_id,
        provider=Provider(str(account.get("provider"))),
        display_name=str(account.get("display_name") or ""),
        primary_email=str(account.get("primary_email")),
        org_type=str(account.get("org_type") or "unknown"),
        timezone=str(account.get("timezone") or "UTC"),
    )


def _classification_input(
    context: AccountContext, row: dict[str, Any], encryptor: FieldEncryptor
) -> ClassificationInput:
    labels_value = row.get("labels")
    labels = [str(label) for label in labels_value] if isinstance(labels_value, list) else []
    return ClassificationInput(
        account_context=context,
        message_id=str(row["id"]),
        sender=EmailAddress(address=str(row.get("sender_email"))),
        subject=str(row.get("subject") or ""),
        body_excerpt=_body_excerpt(row.get("body_ciphertext"), encryptor),
        labels=labels,
    )


def _body_excerpt(ciphertext: Any, encryptor: FieldEncryptor) -> str:
    """Bounded plaintext excerpt; the full body never leaves this function."""
    if not isinstance(ciphertext, str) or not ciphertext:
        return ""
    try:
        body = encryptor.decrypt_text(ciphertext)
    except InvalidToken as exc:
        msg = (
            "Cannot decrypt a stored email body; ENCRYPTION_KEY_BASE64 does not "
            "match the key used at sync time."
        )
        raise BriefDataError(msg) from exc
    return " ".join(body.split())[:EXCERPT_CHARS]


def _stored_classification(row: dict[str, Any]) -> Classification | None:
    if row.get("urgency") is None:
        return None
    payload = row.get("classification")
    if not isinstance(payload, dict) or not payload:
        return None
    try:
        return Classification.model_validate(payload)
    except ValidationError:
        return None  # reclassify rows written under an older contract


def _persist_classification(
    gateway: TableGateway, email_id: str, classification: Classification
) -> None:
    gateway.update_rows(
        EMAILS_TABLE,
        {
            "classification": classification.model_dump(mode="json"),
            "sender_taxonomy": classification.sender_taxonomy.value,
            "urgency": classification.urgency.value,
            "updated_at": datetime.now(tz=UTC).isoformat(),
        },
        eq={"id": email_id},
    )


def _build_proposals(
    supervisor: EmailSupervisor,
    account_id: str,
    rows: list[dict[str, Any]],
    classified: dict[str, Classification],
    rules: list[FilingRule],
) -> list[FilingProposal]:
    proposals: list[FilingProposal] = []
    for row in _rows_by_urgency(rows, classified):
        email_id = str(row["id"])
        classification = classified[email_id]
        decision = supervisor.propose_filing(classification, rules)
        proposals.append(
            FilingProposal(
                proposal_id=_stable_proposal_id(account_id, email_id, decision.proposed_path),
                message_id=email_id,
                subject=str(row.get("subject") or ""),
                urgency=classification.urgency,
                proposed_path=decision.proposed_path,
                requires_review=decision.requires_review,
                rationale=decision.rationale,
            )
        )
    return proposals


def _stable_proposal_id(account_id: str, email_id: str, path: list[str]) -> str:
    digest = sha256(f"{account_id}:{email_id}:{'/'.join(path)}".encode())
    return digest.hexdigest()[:12]


def _rows_by_urgency(
    rows: list[dict[str, Any]], classified: dict[str, Classification]
) -> list[dict[str, Any]]:
    def sort_key(row: dict[str, Any]) -> tuple[int, float]:
        classification = classified[str(row["id"])]
        return (URGENCY_ORDER[classification.urgency], -_timestamp(row).timestamp())

    return sorted(rows, key=sort_key)


def _build_threads(
    rows: list[dict[str, Any]],
    classified: dict[str, Classification],
    profile_id: str,
    account_zone: ZoneInfo,
) -> list[BriefThreadSummary]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("thread_id")), []).append(row)
    threads: list[BriefThreadSummary] = []
    for thread_id, members in grouped.items():
        members.sort(key=_timestamp)
        latest = members[-1]
        urgency = min(
            (classified[str(member["id"])].urgency for member in members),
            key=lambda band: URGENCY_ORDER[band],
        )
        senders: list[str] = []
        for member in members:
            sender = str(member.get("sender_email"))
            if sender not in senders:
                senders.append(sender)
        threads.append(
            BriefThreadSummary(
                thread_id=thread_id,
                subject=str(latest.get("subject") or ""),
                senders=senders,
                profile_id=profile_id,
                urgency=urgency,
                message_count=len(members),
                latest_at=_timestamp(latest).astimezone(account_zone),
            )
        )
    threads.sort(key=lambda thread: (URGENCY_ORDER[thread.urgency], -thread.latest_at.timestamp()))
    return threads


def _timestamp(row: dict[str, Any]) -> datetime:
    value = datetime.fromisoformat(str(row.get("message_timestamp")))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def _account_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")
