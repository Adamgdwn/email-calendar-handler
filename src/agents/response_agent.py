from __future__ import annotations

from src.models.persona_models import DraftRequest, DraftResponse


class ResponseAgent:
    """Prepare human-reviewed draft suggestions from full thread context."""

    system_prompt_budget_tokens = 800
    retrieved_context_budget_tokens = 1_200

    def run(self, request: DraftRequest) -> DraftResponse:
        return DraftResponse(
            thread_id=request.thread_id,
            subject_recommendation="Re: pending review",
            body="Draft generation is not implemented in Milestone 1.1.",
            suggested_send_timing="After human review",
            human_approved=False,
        )
