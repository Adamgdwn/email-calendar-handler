from __future__ import annotations

from src.models.feedback_models import FeedbackRecord
from src.models.filing_models import FilingRule


class LearningAgent:
    """Only approved writer path for promoting or updating filing rules."""

    system_prompt_budget_tokens = 300
    retrieved_context_budget_tokens = 400

    def run(
        self,
        feedback: list[FeedbackRecord],
        current_rules: list[FilingRule],
    ) -> list[FilingRule]:
        _ = feedback
        return current_rules
