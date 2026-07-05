"""Close the feedback loop: review filing proposals, learn from the decisions.

`inboxmind review` presents the same proposals the Morning Brief showed (via
the shared `build_proposal_context`), records each accept/modify/reject as a
`FeedbackRecord`, then hands all of an account's feedback to the LearningAgent,
which promotes or retires filing rules. LearningAgent output is the only thing
written back to `filing_rules`. No mailbox state is ever touched.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, Field

from src.agents.learning_agent import LearningAgent
from src.brief_service import DEFAULT_LOOKBACK_HOURS, build_proposal_context
from src.memory.feedback_store import (
    FILING_TARGET_TYPE,
    acceptance_stats,
    load_feedback,
    record_feedback,
)
from src.memory.rule_store import SupabaseRuleStore
from src.memory.supabase_client import TableGateway
from src.models.brief_models import FilingAcceptanceStats, FilingProposal
from src.models.feedback_models import FeedbackDecision, FeedbackRecord
from src.models.filing_models import FilingRuleStatus
from src.models.persona_models import PersonaProfile
from src.utils.encryption import FieldEncryptor


class ReviewInput(BaseModel):
    """One reviewer's response to a proposal; `decision=None` means skip it."""

    decision: FeedbackDecision | None = None
    modified_path: list[str] | None = Field(default=None, min_length=1)
    note: str | None = None


class ReviewPrompter(Protocol):
    def review(self, proposal: FilingProposal) -> ReviewInput:
        """Ask the human how to handle one filing proposal."""


class ReviewReport(BaseModel):
    account_email: str
    reviewed: int = Field(ge=0)
    accepted: int = Field(ge=0)
    modified: int = Field(ge=0)
    rejected: int = Field(ge=0)
    feedback_recorded: int = Field(ge=0)
    rules_written: int = Field(ge=0)
    promoted_paths: list[str] = Field(default_factory=list)
    retired_paths: list[str] = Field(default_factory=list)
    acceptance: FilingAcceptanceStats = Field(default_factory=FilingAcceptanceStats)


def run_review(
    *,
    gateway: TableGateway,
    encryptor: FieldEncryptor,
    personas: dict[str, PersonaProfile],
    prompter: ReviewPrompter,
    profile_override: str | None = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    now: datetime | None = None,
) -> ReviewReport:
    ctx = build_proposal_context(
        gateway=gateway,
        encryptor=encryptor,
        personas=personas,
        profile_override=profile_override,
        lookback_hours=lookback_hours,
        now=now,
    )
    records = _collect_feedback(ctx.account_id, ctx.moment, ctx.proposals, prompter)
    feedback_recorded = record_feedback(gateway, records)
    all_feedback = load_feedback(gateway, ctx.account_id, target_type=FILING_TARGET_TYPE)
    changed = LearningAgent().run(ctx.account_id, all_feedback, ctx.rules)
    rules_written = SupabaseRuleStore(gateway).save_rules(ctx.account_id, changed)
    return ReviewReport(
        account_email=str(ctx.account.get("primary_email")),
        reviewed=len(records),
        accepted=_count(records, FeedbackDecision.ACCEPT),
        modified=_count(records, FeedbackDecision.MODIFY),
        rejected=_count(records, FeedbackDecision.REJECT),
        feedback_recorded=feedback_recorded,
        rules_written=rules_written,
        promoted_paths=[
            "/".join(rule.path) for rule in changed if rule.status is FilingRuleStatus.CONFIRMED
        ],
        retired_paths=[
            "/".join(rule.path) for rule in changed if rule.status is FilingRuleStatus.RETIRED
        ],
        acceptance=acceptance_stats(gateway, ctx.account_id),
    )


def _collect_feedback(
    account_id: str,
    moment: datetime,
    proposals: list[FilingProposal],
    prompter: ReviewPrompter,
) -> list[FeedbackRecord]:
    records: list[FeedbackRecord] = []
    for index, proposal in enumerate(proposals):
        response = prompter.review(proposal)
        if response.decision is None:
            continue
        final_path = response.modified_path or proposal.proposed_path
        records.append(
            FeedbackRecord(
                feedback_id=f"pending:{proposal.proposal_id}",
                account_id=account_id,
                target_type=FILING_TARGET_TYPE,
                target_id=proposal.proposal_id,
                decision=response.decision,
                user_note=response.note,
                # A stable per-item offset keeps same-run decisions ordered for
                # the LearningAgent even though they share one `moment`.
                created_at=moment + timedelta(microseconds=index),
                context={
                    "path": "/".join(final_path),
                    "message_id": proposal.message_id,
                    "proposed_path": "/".join(proposal.proposed_path),
                },
            )
        )
    return records


def _count(records: list[FeedbackRecord], decision: FeedbackDecision) -> int:
    return sum(1 for record in records if record.decision is decision)
