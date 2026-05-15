from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class FeedbackDecision(StrEnum):
    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"


class FeedbackRecord(BaseModel):
    feedback_id: str
    account_id: str
    target_type: str
    target_id: str
    decision: FeedbackDecision
    user_note: str | None = None
    created_at: datetime
    context: dict[str, str] = Field(default_factory=dict)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "created_at must be timezone-aware"
            raise ValueError(msg)
        return value
