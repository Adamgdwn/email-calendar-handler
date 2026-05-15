from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievedDecision(BaseModel):
    account_id: str
    source_id: str
    summary: str
    similarity_score: float = Field(ge=0, le=1)


class VectorStore:
    """Supabase pgvector access placeholder with account-scoped retrieval."""

    def search_past_decisions(
        self,
        account_id: str,
        query: str,
        top_k: int = 3,
    ) -> list[RetrievedDecision]:
        _ = account_id
        _ = query
        _ = top_k
        return []
