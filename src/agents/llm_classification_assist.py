"""LLM-assisted classification for emails that fall below deterministic confidence.

The deterministic ClassificationAgent remains authoritative for high-confidence
results. This module is only invoked when confidence < threshold and
LLM_ASSIST_ENABLED is explicitly set to true. Opt-in only — never the default.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from src.llm.anthropic_client import LLMClient
from src.models.email_models import (
    Classification,
    ClassificationInput,
    SenderTaxonomy,
    UrgencyBand,
)

logger = logging.getLogger(__name__)

LLM_ASSIST_THRESHOLD_DEFAULT = 0.6
LLM_ASSIST_DAILY_BUDGET_DEFAULT = 10_000


@dataclass(frozen=True)
class LLMAssistConfig:
    """Configuration for opt-in LLM classification assist.

    Only constructed when LLM_ASSIST_ENABLED=true. When absent, the deterministic
    path runs exclusively.
    """

    confidence_threshold: float
    daily_token_budget: int
    api_key: str
    budget_path: Path


class _LLMClassificationResponse(BaseModel):
    urgency: UrgencyBand
    sender_taxonomy: SenderTaxonomy
    reasons: list[str] = Field(default_factory=list, max_length=3)


_SYSTEM_PROMPT = (
    "You are an email classifier for a busy professional. "
    "Classify the email using only the provided metadata and excerpt — "
    "no email body is available beyond the excerpt. "
    "Respond with valid JSON only — no markdown, no explanation.\n"
    'Schema: {"urgency": "critical|high|normal|low", '
    '"sender_taxonomy": "internal|external_known|external_unknown", '
    '"reasons": ["short reason 1", "short reason 2"]}'
)


class LLMClassificationAssist:
    """Single-purpose LLM fallback for low-confidence deterministic results.

    Body boundary discipline is preserved: only the 500-char excerpt and
    metadata fields from ClassificationInput are included in the prompt.
    Returns (classification, tokens_used); on any failure returns the
    deterministic classification unchanged with 0 tokens.
    """

    max_response_tokens: int = 150

    def classify(
        self,
        item: ClassificationInput,
        llm_client: LLMClient,
        deterministic: Classification,
    ) -> tuple[Classification, int]:
        try:
            response = llm_client.complete(
                system=_SYSTEM_PROMPT,
                user=self._build_prompt(item),
                max_tokens=self.max_response_tokens,
            )
        except Exception:
            logger.warning("LLM classification call failed; keeping deterministic result")
            return deterministic, 0

        tokens = response.input_tokens + response.output_tokens
        return self._parse(response.text, item, deterministic), tokens

    def _build_prompt(self, item: ClassificationInput) -> str:
        labels = ", ".join(item.labels) if item.labels else "none"
        return (
            f"Subject: {item.subject}\n"
            f"Sender: {item.sender.address}\n"
            f"Labels: {labels}\n"
            f"Excerpt: {item.body_excerpt}"
        )

    def _parse(
        self,
        text: str,
        item: ClassificationInput,
        deterministic: Classification,
    ) -> Classification:
        try:
            data = json.loads(text.strip())
            parsed = _LLMClassificationResponse.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            logger.warning(
                "LLM classification response did not parse; keeping deterministic result"
            )
            return deterministic

        reasons = (
            list(parsed.reasons) + [f"persona:{item.account_context.profile_id}", "method:llm"]
        )[:5]
        return Classification(
            message_id=item.message_id,
            sender_taxonomy=parsed.sender_taxonomy,
            urgency=parsed.urgency,
            org_type=item.account_context.org_type,
            confidence_score=0.75,
            reasons=reasons,
        )
