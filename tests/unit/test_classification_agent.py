from src.agents.classification_agent import ClassificationAgent
from src.models.email_models import (
    AccountContext,
    ClassificationInput,
    EmailAddress,
    Provider,
    SenderTaxonomy,
    UrgencyBand,
)


def test_classification_uses_excerpt_only_contract() -> None:
    account = AccountContext(
        account_id="acct-1",
        profile_id="prime_boilers",
        provider=Provider.GMAIL,
        display_name="Prime Boilers",
        primary_email="ops@primeboilers.example",
        org_type="commercial",
    )
    item = ClassificationInput(
        account_context=account,
        message_id="msg-1",
        sender=EmailAddress(address="client@example.com"),
        subject="Emergency site shutdown",
        body_excerpt="Need help today.",
        labels=["INBOX"],
    )

    result = ClassificationAgent().run(item)

    assert result.urgency == UrgencyBand.CRITICAL
    assert result.sender_taxonomy == SenderTaxonomy.EXTERNAL_UNKNOWN
    assert result.org_type == "commercial"
