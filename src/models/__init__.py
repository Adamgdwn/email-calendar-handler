"""Pydantic contracts for InboxMind."""

from src.models.auth_models import OAuthConsentRecord
from src.models.email_models import (
    AccountContext,
    Classification,
    ClassificationInput,
    EmailAddress,
    EmailThread,
    RawEmail,
    SenderTaxonomy,
    UrgencyBand,
)
from src.models.filing_models import FilingDecision, FilingRule, FilingTaxonomyNode
from src.models.persona_models import PersonaProfile

__all__ = [
    "AccountContext",
    "Classification",
    "ClassificationInput",
    "EmailAddress",
    "EmailThread",
    "FilingDecision",
    "FilingRule",
    "FilingTaxonomyNode",
    "OAuthConsentRecord",
    "PersonaProfile",
    "RawEmail",
    "SenderTaxonomy",
    "UrgencyBand",
]
