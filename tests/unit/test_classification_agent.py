import pytest
from pydantic import ValidationError

from src.agents.classification_agent import (
    KEYWORD_CONFIDENCE,
    NO_MATCH_CONFIDENCE,
    ClassificationAgent,
)
from src.models.email_models import (
    AccountContext,
    ClassificationInput,
    EmailAddress,
    Provider,
    SenderTaxonomy,
    UrgencyBand,
)
from src.models.persona_models import PersonaProfile


def make_persona() -> PersonaProfile:
    return PersonaProfile(
        profile_id="prime_boilers",
        display_name="Prime Boilers",
        tone="direct",
        urgency_definitions={
            UrgencyBand.CRITICAL: ["shutdown", "emergency"],
            UrgencyBand.HIGH: ["quote", "inspection"],
            UrgencyBand.NORMAL: ["update", "follow up"],
        },
        filing_taxonomy="commercial.yaml",
    )


def make_input(
    subject: str, excerpt: str = "", sender: str = "client@example.com"
) -> ClassificationInput:
    account = AccountContext(
        account_id="acct-1",
        profile_id="prime_boilers",
        provider=Provider.MICROSOFT_GRAPH,
        display_name="Prime Boilers",
        primary_email="ops@primeboilers.example",
        org_type="commercial",
    )
    return ClassificationInput(
        account_context=account,
        message_id="msg-1",
        sender=EmailAddress(address=sender),
        subject=subject,
        body_excerpt=excerpt,
        labels=["INBOX"],
    )


def test_persona_critical_keyword_drives_band_and_reason() -> None:
    result = ClassificationAgent(make_persona()).run(make_input("Emergency site shutdown"))

    assert result.urgency == UrgencyBand.CRITICAL
    assert result.confidence_score == KEYWORD_CONFIDENCE
    assert "matched_critical:shutdown" in result.reasons
    assert "persona:prime_boilers" in result.reasons


def test_high_and_normal_bands_come_from_persona_definitions() -> None:
    agent = ClassificationAgent(make_persona())

    assert agent.run(make_input("Quote request for the boiler room")).urgency == UrgencyBand.HIGH
    assert agent.run(make_input("Weekly update")).urgency == UrgencyBand.NORMAL


def test_no_keyword_match_lands_low_with_baseline_confidence() -> None:
    result = ClassificationAgent(make_persona()).run(make_input("Lunch on Friday?"))

    assert result.urgency == UrgencyBand.LOW
    assert result.confidence_score == NO_MATCH_CONFIDENCE
    assert "no_urgency_keywords" in result.reasons


def test_excerpt_contributes_to_urgency() -> None:
    result = ClassificationAgent(make_persona()).run(
        make_input("Re: site visit", excerpt="The inspection is booked for Monday.")
    )

    assert result.urgency == UrgencyBand.HIGH


def test_sender_taxonomy_by_domain() -> None:
    agent = ClassificationAgent(make_persona())

    internal = agent.run(make_input("Weekly update", sender="teammate@primeboilers.example"))
    external = agent.run(make_input("Weekly update", sender="client@example.com"))

    assert internal.sender_taxonomy == SenderTaxonomy.INTERNAL
    assert external.sender_taxonomy == SenderTaxonomy.EXTERNAL_UNKNOWN


def test_excerpt_only_contract_still_enforced_at_the_boundary() -> None:
    with pytest.raises(ValidationError):
        make_input("subject", excerpt="x" * 501)
