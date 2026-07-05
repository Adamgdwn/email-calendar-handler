"""Persist and read review feedback.

Every `inboxmind review` decision lands here as one `feedback` row. The
LearningAgent reads these back to promote or retire filing rules, and the
Morning Brief footer reads the acceptance rate that governs the write-scope
gate. Writes never touch the mailbox and never carry raw email bodies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.memory.supabase_client import TableGateway
from src.models.brief_models import FilingAcceptanceStats
from src.models.feedback_models import FeedbackDecision, FeedbackRecord

FEEDBACK_TABLE = "feedback"
FILING_TARGET_TYPE = "filing_proposal"
FEEDBACK_COLUMNS = "id,account_id,target_type,target_id,decision,user_note,context,created_at"


def record_feedback(gateway: TableGateway, records: list[FeedbackRecord]) -> int:
    """Insert one row per review decision; returns the number written."""
    if not records:
        return 0
    payloads = [
        {
            "account_id": record.account_id,
            "target_type": record.target_type,
            "target_id": record.target_id,
            "decision": record.decision.value,
            "user_note": record.user_note,
            "context": record.context,
            "created_at": record.created_at.astimezone(UTC).isoformat(),
        }
        for record in records
    ]
    gateway.insert_rows(FEEDBACK_TABLE, payloads)
    return len(payloads)


def load_feedback(
    gateway: TableGateway, account_id: str, *, target_type: str | None = None
) -> list[FeedbackRecord]:
    """Return an account's feedback, oldest first, for the LearningAgent to fold."""
    rows = gateway.select_rows(FEEDBACK_TABLE, FEEDBACK_COLUMNS, eq={"account_id": account_id})
    records = [_to_record(row) for row in rows]
    if target_type is not None:
        records = [record for record in records if record.target_type == target_type]
    records.sort(key=lambda record: record.created_at)
    return records


def acceptance_stats(
    gateway: TableGateway, account_id: str, *, target_type: str = FILING_TARGET_TYPE
) -> FilingAcceptanceStats:
    """Accept rate over reviewed proposals; the write-scope gate reads this."""
    records = load_feedback(gateway, account_id, target_type=target_type)
    accepted = sum(1 for record in records if record.decision is FeedbackDecision.ACCEPT)
    return FilingAcceptanceStats(total=len(records), accepted=accepted)


def _to_record(row: dict[str, Any]) -> FeedbackRecord:
    context_value = row.get("context")
    context = (
        {str(key): str(value) for key, value in context_value.items()}
        if isinstance(context_value, dict)
        else {}
    )
    return FeedbackRecord(
        feedback_id=str(row.get("id")),
        account_id=str(row.get("account_id")),
        target_type=str(row.get("target_type")),
        target_id=str(row.get("target_id")),
        decision=FeedbackDecision(str(row.get("decision"))),
        user_note=_optional_str(row.get("user_note")),
        created_at=_parse_instant(row.get("created_at")),
        context=context,
    )


def _optional_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _parse_instant(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
