from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.learning_agent import LearningAgent
from src.models.feedback_models import FeedbackDecision, FeedbackRecord
from src.models.filing_models import FilingRule, FilingRuleStatus

ACCOUNT_ID = "acct-1"
BASE = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)


def fb(path: str, decision: FeedbackDecision, seconds: int) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=f"f-{seconds}",
        account_id=ACCOUNT_ID,
        target_type="filing_proposal",
        target_id=f"p-{seconds}",
        decision=decision,
        created_at=BASE + timedelta(seconds=seconds),
        context={"path": path},
    )


def confirmed_rule(rule_id: str, path: list[str], *, human_approved: bool = False) -> FilingRule:
    return FilingRule(
        rule_id=rule_id,
        account_id=ACCOUNT_ID,
        path=path,
        status=FilingRuleStatus.CONFIRMED,
        confidence_score=0.9,
        human_approved=human_approved,
    )


def test_three_consecutive_accepts_confirm_a_new_rule() -> None:
    feedback = [fb("Clients/Acme", FeedbackDecision.ACCEPT, i) for i in range(3)]

    rules = LearningAgent().run(ACCOUNT_ID, feedback, current_rules=[])

    assert len(rules) == 1
    assert rules[0].path == ["Clients", "Acme"]
    assert rules[0].status is FilingRuleStatus.CONFIRMED
    assert rules[0].account_id == ACCOUNT_ID


def test_two_accepts_stay_provisional() -> None:
    feedback = [fb("Clients/Acme", FeedbackDecision.ACCEPT, i) for i in range(2)]

    rules = LearningAgent().run(ACCOUNT_ID, feedback, current_rules=[])

    assert rules[0].status is FilingRuleStatus.PROVISIONAL


def test_confirmation_never_sets_human_approved() -> None:
    feedback = [fb("Clients/Acme", FeedbackDecision.ACCEPT, i) for i in range(5)]

    rules = LearningAgent().run(ACCOUNT_ID, feedback, current_rules=[])

    assert rules[0].status is FilingRuleStatus.CONFIRMED
    assert rules[0].human_approved is False


def test_reject_retires_an_existing_rule_and_keeps_its_id() -> None:
    existing = confirmed_rule("rule-db-1", ["Clients", "Acme"], human_approved=True)
    feedback = [
        fb("Clients/Acme", FeedbackDecision.ACCEPT, 0),
        fb("Clients/Acme", FeedbackDecision.REJECT, 1),
    ]

    rules = LearningAgent().run(ACCOUNT_ID, feedback, current_rules=[existing])

    assert len(rules) == 1
    assert rules[0].rule_id == "rule-db-1"
    assert rules[0].status is FilingRuleStatus.RETIRED


def test_modify_demotes_a_confirmed_rule_to_provisional() -> None:
    existing = confirmed_rule("rule-db-1", ["Clients", "Acme"])
    feedback = [fb("Clients/Acme", FeedbackDecision.ACCEPT, i) for i in range(3)]
    feedback.append(fb("Clients/Acme", FeedbackDecision.MODIFY, 3))

    rules = LearningAgent().run(ACCOUNT_ID, feedback, current_rules=[existing])

    assert rules[0].rule_id == "rule-db-1"
    assert rules[0].status is FilingRuleStatus.PROVISIONAL


def test_existing_provisional_rule_is_promoted_in_place() -> None:
    existing = FilingRule(
        rule_id="rule-db-1",
        account_id=ACCOUNT_ID,
        path=["Clients", "Acme"],
        status=FilingRuleStatus.PROVISIONAL,
        confidence_score=0.5,
    )
    feedback = [fb("Clients/Acme", FeedbackDecision.ACCEPT, i) for i in range(3)]

    rules = LearningAgent().run(ACCOUNT_ID, feedback, current_rules=[existing])

    assert rules[0].rule_id == "rule-db-1"
    assert rules[0].status is FilingRuleStatus.CONFIRMED


def test_paths_are_learned_independently() -> None:
    feedback = [fb("Clients/Acme", FeedbackDecision.ACCEPT, i) for i in range(3)]
    feedback.append(fb("Newsletters", FeedbackDecision.ACCEPT, 3))

    rules = LearningAgent().run(ACCOUNT_ID, feedback, current_rules=[])

    by_path = {tuple(rule.path): rule.status for rule in rules}
    assert by_path[("Clients", "Acme")] is FilingRuleStatus.CONFIRMED
    assert by_path[("Newsletters",)] is FilingRuleStatus.PROVISIONAL


def test_feedback_without_a_path_is_ignored() -> None:
    record = FeedbackRecord(
        feedback_id="f-x",
        account_id=ACCOUNT_ID,
        target_type="other",
        target_id="t",
        decision=FeedbackDecision.ACCEPT,
        created_at=BASE,
        context={},
    )

    assert LearningAgent().run(ACCOUNT_ID, [record], current_rules=[]) == []
