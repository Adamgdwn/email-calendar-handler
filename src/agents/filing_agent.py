from __future__ import annotations

from src.models.email_models import Classification
from src.models.filing_models import FilingDecision, FilingRule


class FilingAgent:
    """Propose filing paths from classification metadata and confirmed rules."""

    system_prompt_budget_tokens = 600
    retrieved_context_budget_tokens = 800

    def run(self, classification: Classification, rules: list[FilingRule]) -> FilingDecision:
        confirmed_rule = next((rule for rule in rules if rule.human_approved), None)
        if confirmed_rule is None:
            return FilingDecision(
                message_id=classification.message_id,
                classification=classification,
                proposed_path=["Review"],
                requires_review=True,
                rationale="No human-approved filing rule is available.",
            )
        return FilingDecision(
            message_id=classification.message_id,
            classification=classification,
            proposed_path=confirmed_rule.path,
            rule_id=confirmed_rule.rule_id,
            human_approved=False,
            requires_review=False,
            rationale="Matched a human-approved filing rule branch.",
        )
