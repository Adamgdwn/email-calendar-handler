from __future__ import annotations

from pydantic import BaseModel, Field


class PersonaProfile(BaseModel):
    profile_id: str
    display_name: str
    tone: str
    urgency_definitions: dict[str, list[str]] = Field(default_factory=dict)
    filing_taxonomy: str
    response_constraints: list[str] = Field(default_factory=list)


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
