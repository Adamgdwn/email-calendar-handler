from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from src.models.email_models import Classification


class FilingRuleStatus(StrEnum):
    PROVISIONAL = "provisional"
    CONFIRMED = "confirmed"
    RETIRED = "retired"


class FilingTaxonomyNode(BaseModel):
    node: str
    children: list[FilingTaxonomyNode] = Field(default_factory=list)


class FilingRule(BaseModel):
    rule_id: str
    account_id: str
    path: list[str] = Field(min_length=1)
    status: FilingRuleStatus
    confidence_score: float = Field(ge=0, le=1)
    human_approved: bool = False
    user_override: bool = False


class FilingDecision(BaseModel):
    message_id: str
    classification: Classification
    proposed_path: list[str] = Field(min_length=1)
    rule_id: str | None = None
    human_approved: bool = False
    requires_review: bool = True
    rationale: str
