from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.models.email_models import UrgencyBand


class PersonaProfile(BaseModel):
    profile_id: str
    display_name: str
    tone: str
    urgency_definitions: dict[UrgencyBand, list[str]] = Field(default_factory=dict)
    filing_taxonomy: str
    response_constraints: list[str] = Field(default_factory=list)

    @field_validator("urgency_definitions")
    @classmethod
    def keywords_must_be_lowercase(
        cls, value: dict[UrgencyBand, list[str]]
    ) -> dict[UrgencyBand, list[str]]:
        """Urgency matching lowercases the text, so definitions must match lowercased."""
        return {band: [keyword.lower() for keyword in keywords] for band, keywords in value.items()}


class DraftRequest(BaseModel):
    account_id: str
    thread_id: str
    persona: PersonaProfile
    human_approved: bool = False


class DraftResponse(BaseModel):
    thread_id: str
    subject_recommendation: str
    body: str
    suggested_send_timing: str
    human_approved: bool = False
