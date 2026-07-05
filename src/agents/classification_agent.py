from __future__ import annotations

from src.models.email_models import Classification, ClassificationInput, SenderTaxonomy, UrgencyBand
from src.models.persona_models import PersonaProfile

KEYWORD_CONFIDENCE = 0.8
NO_MATCH_CONFIDENCE = 0.5
_BAND_PRIORITY = (UrgencyBand.CRITICAL, UrgencyBand.HIGH, UrgencyBand.NORMAL)


class ClassificationAgent:
    """Classify with persona urgency keywords; never receives full email bodies."""

    system_prompt_budget_tokens = 400
    max_body_excerpt_chars = 500

    def __init__(self, persona: PersonaProfile) -> None:
        self._persona = persona

    def run(self, item: ClassificationInput) -> Classification:
        urgency, reason, confidence = self._score_urgency(item.subject, item.body_excerpt)
        sender_taxonomy = self._classify_sender(
            item.sender.address,
            item.account_context.primary_email,
        )
        return Classification(
            message_id=item.message_id,
            sender_taxonomy=sender_taxonomy,
            urgency=urgency,
            org_type=item.account_context.org_type,
            confidence_score=confidence,
            reasons=[reason, f"persona:{self._persona.profile_id}"],
        )

    def _score_urgency(self, subject: str, body_excerpt: str) -> tuple[UrgencyBand, str, float]:
        text = f"{subject} {body_excerpt}".lower()
        for band in _BAND_PRIORITY:
            for keyword in self._persona.urgency_definitions.get(band, []):
                if keyword in text:
                    return band, f"matched_{band.value}:{keyword}", KEYWORD_CONFIDENCE
        return UrgencyBand.LOW, "no_urgency_keywords", NO_MATCH_CONFIDENCE

    def _classify_sender(self, sender: str, account_email: str) -> SenderTaxonomy:
        sender_domain = sender.split("@")[-1].lower()
        account_domain = account_email.split("@")[-1].lower()
        if sender_domain == account_domain:
            return SenderTaxonomy.INTERNAL
        return SenderTaxonomy.EXTERNAL_UNKNOWN
