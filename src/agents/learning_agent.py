from __future__ import annotations

from hashlib import sha256

from src.models.feedback_models import FeedbackDecision, FeedbackRecord
from src.models.filing_models import FilingRule, FilingRuleStatus

PROMOTION_STREAK = 3
_PROVISIONAL_CONFIDENCE = 0.5
_STEP_PER_ACCEPT = 0.1
_RETIRED_CONFIDENCE = 0.1


class LearningAgent:
    """Only approved writer path for promoting or updating filing rules.

    Folds review feedback into rule statuses deterministically, keyed on the
    filing path a proposal targeted:
    - three consecutive accepts confirm a rule (promotion),
    - a most-recent reject retires it,
    - anything short of a streak (including a modify that breaks one) leaves or
      returns the rule to provisional (demotion).
    It never sets `human_approved`; that gate stays with the human, so a
    confirmed rule still needs explicit approval before FilingAgent trusts it.
    """

    system_prompt_budget_tokens = 300
    retrieved_context_budget_tokens = 400

    def run(
        self,
        account_id: str,
        feedback: list[FeedbackRecord],
        current_rules: list[FilingRule],
    ) -> list[FilingRule]:
        """Return the rules whose status changed or were newly learned."""
        grouped = _group_by_path(feedback)
        existing_by_path = {tuple(rule.path): rule for rule in current_rules}
        updated: list[FilingRule] = []
        for path, decisions in grouped.items():
            status, confidence = _evaluate(decisions)
            existing = existing_by_path.get(path)
            if existing is not None:
                updated.append(
                    existing.model_copy(update={"status": status, "confidence_score": confidence})
                )
            else:
                updated.append(
                    FilingRule(
                        rule_id=_provisional_rule_id(account_id, path),
                        account_id=account_id,
                        path=list(path),
                        status=status,
                        confidence_score=confidence,
                        human_approved=False,
                        user_override=False,
                    )
                )
        return updated


def _group_by_path(
    feedback: list[FeedbackRecord],
) -> dict[tuple[str, ...], list[FeedbackDecision]]:
    ordered = sorted(feedback, key=lambda record: record.created_at)
    grouped: dict[tuple[str, ...], list[FeedbackDecision]] = {}
    for record in ordered:
        path_value = record.context.get("path")
        if not path_value:
            continue
        grouped.setdefault(tuple(path_value.split("/")), []).append(record.decision)
    return grouped


def _evaluate(decisions: list[FeedbackDecision]) -> tuple[FilingRuleStatus, float]:
    if decisions and decisions[-1] is FeedbackDecision.REJECT:
        return FilingRuleStatus.RETIRED, _RETIRED_CONFIDENCE
    streak = 0
    for decision in reversed(decisions):
        if decision is FeedbackDecision.ACCEPT:
            streak += 1
        else:
            break
    confidence = min(1.0, _PROVISIONAL_CONFIDENCE + _STEP_PER_ACCEPT * streak)
    if streak >= PROMOTION_STREAK:
        return FilingRuleStatus.CONFIRMED, confidence
    return FilingRuleStatus.PROVISIONAL, confidence


def _provisional_rule_id(account_id: str, path: tuple[str, ...]) -> str:
    digest = sha256(f"{account_id}:{'/'.join(path)}".encode())
    return f"learned-{digest.hexdigest()[:12]}"
