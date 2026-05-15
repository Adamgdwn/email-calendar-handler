from src.agents.filing_agent import FilingAgent
from src.models.email_models import Classification, SenderTaxonomy, UrgencyBand
from src.models.filing_models import FilingRule, FilingRuleStatus


def test_filing_requires_review_without_human_approved_rule() -> None:
    classification = Classification(
        message_id="msg-1",
        sender_taxonomy=SenderTaxonomy.EXTERNAL_UNKNOWN,
        urgency=UrgencyBand.NORMAL,
        org_type="commercial",
        confidence_score=0.75,
    )

    decision = FilingAgent().run(classification, rules=[])

    assert decision.requires_review is True
    assert decision.human_approved is False
    assert decision.proposed_path == ["Review"]


def test_filing_can_apply_confirmed_rule_but_does_not_approve_action() -> None:
    classification = Classification(
        message_id="msg-1",
        sender_taxonomy=SenderTaxonomy.EXTERNAL_UNKNOWN,
        urgency=UrgencyBand.NORMAL,
        org_type="commercial",
        confidence_score=0.75,
    )
    rule = FilingRule(
        rule_id="rule-1",
        account_id="acct-1",
        path=["Clients", "Example", "Correspondence"],
        status=FilingRuleStatus.CONFIRMED,
        confidence_score=0.95,
        human_approved=True,
    )

    decision = FilingAgent().run(classification, rules=[rule])

    assert decision.proposed_path == ["Clients", "Example", "Correspondence"]
    assert decision.requires_review is False
    assert decision.human_approved is False
