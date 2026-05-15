from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class EmailAddress(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = None
    address: EmailStr


class Provider(StrEnum):
    GMAIL = "gmail"
    MICROSOFT_GRAPH = "microsoft_graph"


class SenderTaxonomy(StrEnum):
    INTERNAL = "internal"
    EXTERNAL_KNOWN = "external_known"
    EXTERNAL_UNKNOWN = "external_unknown"


class UrgencyBand(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class AccountContext(BaseModel):
    account_id: str
    profile_id: str
    provider: Provider
    display_name: str
    primary_email: EmailStr
    org_type: str
    timezone: str = "America/Edmonton"


class RawEmail(BaseModel):
    message_id: str
    thread_id: str
    sender: EmailAddress
    recipients: list[EmailAddress]
    subject: str
    body_text: str
    timestamp: datetime
    labels: list[str] = Field(default_factory=list)

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "timestamp must be timezone-aware"
            raise ValueError(msg)
        return value


class EmailThread(BaseModel):
    thread_id: str
    messages: list[RawEmail]
    participant_set: set[str]
    duration_days: float = Field(ge=0)
    last_activity: datetime

    @field_validator("last_activity")
    @classmethod
    def last_activity_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "last_activity must be timezone-aware"
            raise ValueError(msg)
        return value


class ClassificationInput(BaseModel):
    account_context: AccountContext
    message_id: str
    sender: EmailAddress
    subject: str
    body_excerpt: str = Field(max_length=500)
    labels: list[str] = Field(default_factory=list)


class Classification(BaseModel):
    message_id: str
    sender_taxonomy: SenderTaxonomy
    urgency: UrgencyBand
    org_type: str
    confidence_score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list, max_length=5)
