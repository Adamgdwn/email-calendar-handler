"""Typed contracts for the Morning Brief artifact."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from src.models.calendar_models import CalendarEvent
from src.models.email_models import UrgencyBand

URGENCY_ORDER: dict[UrgencyBand, int] = {
    UrgencyBand.CRITICAL: 0,
    UrgencyBand.HIGH: 1,
    UrgencyBand.NORMAL: 2,
    UrgencyBand.LOW: 3,
}


class BriefThreadSummary(BaseModel):
    thread_id: str
    subject: str
    senders: list[str] = Field(min_length=1)
    profile_id: str
    urgency: UrgencyBand
    message_count: int = Field(ge=1)
    latest_at: datetime
    boost_reason: str | None = None

    @field_validator("latest_at")
    @classmethod
    def latest_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "latest_at must be timezone-aware"
            raise ValueError(msg)
        return value


class FilingProposal(BaseModel):
    proposal_id: str
    message_id: str
    subject: str
    urgency: UrgencyBand
    proposed_path: list[str] = Field(min_length=1)
    requires_review: bool
    rationale: str


class FilingAcceptanceStats(BaseModel):
    """Proposal-review outcomes for one account; drives the write-scope gate."""

    total: int = Field(default=0, ge=0)
    accepted: int = Field(default=0, ge=0)

    @property
    def rate(self) -> float:
        return self.accepted / self.total if self.total else 0.0


class MorningBrief(BaseModel):
    brief_date: date
    account_email: str
    profile_id: str
    persona_display_name: str
    lookback_hours: int = Field(ge=1)
    generated_at: datetime
    events: list[CalendarEvent] = Field(default_factory=list)
    threads: list[BriefThreadSummary] = Field(default_factory=list)
    proposals: list[FilingProposal] = Field(default_factory=list)
    acceptance: FilingAcceptanceStats = Field(default_factory=FilingAcceptanceStats)
    classified_now: int = Field(ge=0)
    previously_classified: int = Field(ge=0)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "generated_at must be timezone-aware"
            raise ValueError(msg)
        return value
