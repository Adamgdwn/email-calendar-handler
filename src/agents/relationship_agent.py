from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.email_models import AccountContext, EmailThread


class RelationshipEdge(BaseModel):
    source_contact: str
    target_contact: str
    weight: float = Field(ge=0)


class RelationshipGraphSnapshot(BaseModel):
    account_id: str
    edges: list[RelationshipEdge] = Field(default_factory=list)


class RelationshipAgent:
    """Build incremental relationship graph snapshots from typed threads."""

    system_prompt_budget_tokens = 300

    def run(
        self,
        account_context: AccountContext,
        threads: list[EmailThread],
    ) -> RelationshipGraphSnapshot:
        _ = threads
        return RelationshipGraphSnapshot(account_id=account_context.account_id)
