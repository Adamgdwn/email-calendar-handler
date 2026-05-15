from __future__ import annotations

from src.models.email_models import Classification, ClassificationInput, SenderTaxonomy, UrgencyBand


class ClassificationAgent:
    """Classify email metadata without receiving full email bodies."""

    system_prompt_budget_tokens = 400
    max_body_excerpt_chars = 500

    def run(self, item: ClassificationInput) -> Classification:
        urgency = self._score_urgency(item.subject, item.body_excerpt)
        sender_taxonomy = self._classify_sender(
            item.sender.address,
            item.account_context.primary_email,
        )
        return Classification(
            message_id=item.message_id,
            sender_taxonomy=sender_taxonomy,
            urgency=urgency,
            org_type=item.account_context.org_type,
            confidence_score=0.65,
            reasons=["rule_based_baseline"],
        )

    def _score_urgency(self, subject: str, body_excerpt: str) -> UrgencyBand:
        text = f"{subject} {body_excerpt}".lower()
        critical_terms = ("urgent", "asap", "deadline", "shutdown", "emergency")
        high_terms = ("today", "tomorrow", "reply all", "approval")
        if any(term in text for term in critical_terms):
            return UrgencyBand.CRITICAL
        if any(term in text for term in high_terms):
            return UrgencyBand.HIGH
        return UrgencyBand.NORMAL

    def _classify_sender(self, sender: str, account_email: str) -> SenderTaxonomy:
        sender_domain = sender.split("@")[-1].lower()
        account_domain = account_email.split("@")[-1].lower()
        if sender_domain == account_domain:
            return SenderTaxonomy.INTERNAL
        return SenderTaxonomy.EXTERNAL_UNKNOWN
