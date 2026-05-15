from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.models.email_models import Provider


class OAuthConsentRecord(BaseModel):
    provider: Provider
    account_id: str
    subject: str
    scopes: list[str] = Field(min_length=1)
    granted_at: datetime
    tenant_id: str | None = None
    human_confirmed: bool = True

    @field_validator("granted_at")
    @classmethod
    def granted_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "granted_at must be timezone-aware"
            raise ValueError(msg)
        return value

    @field_validator("human_confirmed")
    @classmethod
    def consent_must_be_human_confirmed(cls, value: bool) -> bool:
        if value is not True:
            msg = "OAuth consent must be explicitly confirmed by a human"
            raise ValueError(msg)
        return value
