"""Tests for LLMClassificationAssist and DailyTokenBudget."""

from __future__ import annotations

import json
from pathlib import Path

from src.agents.llm_classification_assist import LLMClassificationAssist
from src.llm.anthropic_client import FakeLLMClient, LLMResponse
from src.models.email_models import (
    AccountContext,
    Classification,
    ClassificationInput,
    EmailAddress,
    Provider,
    SenderTaxonomy,
    UrgencyBand,
)
from src.utils.daily_token_budget import DailyTokenBudget

# ── fixtures ──────────────────────────────────────────────────────────────────

_CONTEXT = AccountContext(
    account_id="acc-1",
    profile_id="test",
    provider=Provider.MICROSOFT_GRAPH,
    display_name="Test Account",
    primary_email="user@example.com",
    org_type="organization",
)

_ITEM = ClassificationInput(
    account_context=_CONTEXT,
    message_id="msg-1",
    sender=EmailAddress(address="boss@client.com"),
    subject="Urgent: Contract Review",
    body_excerpt="Please review the attached contract by end of day.",
    labels=["Inbox"],
)

_DETERMINISTIC = Classification(
    message_id="msg-1",
    sender_taxonomy=SenderTaxonomy.EXTERNAL_UNKNOWN,
    urgency=UrgencyBand.LOW,
    org_type="organization",
    confidence_score=0.5,
    reasons=["no_urgency_keywords", "persona:test"],
)


# ── LLMClassificationAssist ───────────────────────────────────────────────────


def test_classify_uses_llm_response() -> None:
    resp = '{"urgency": "high", "sender_taxonomy": "external_known", "reasons": ["deadline"]}'
    llm = FakeLLMClient(resp)
    result, tokens = LLMClassificationAssist().classify(_ITEM, llm, _DETERMINISTIC)
    assert result.urgency == UrgencyBand.HIGH
    assert result.sender_taxonomy == SenderTaxonomy.EXTERNAL_KNOWN
    assert tokens > 0


def test_method_tag_in_reasons() -> None:
    llm = FakeLLMClient('{"urgency": "critical", "sender_taxonomy": "internal", "reasons": []}')
    result, _ = LLMClassificationAssist().classify(_ITEM, llm, _DETERMINISTIC)
    assert "method:llm" in result.reasons


def test_persona_tag_in_reasons() -> None:
    llm = FakeLLMClient(
        '{"urgency": "normal", "sender_taxonomy": "external_unknown", "reasons": []}'
    )
    result, _ = LLMClassificationAssist().classify(_ITEM, llm, _DETERMINISTIC)
    assert "persona:test" in result.reasons


def test_reasons_within_max_length() -> None:
    llm = FakeLLMClient(
        '{"urgency": "normal", "sender_taxonomy": "external_unknown", '
        '"reasons": ["r1", "r2", "r3"]}'
    )
    result, _ = LLMClassificationAssist().classify(_ITEM, llm, _DETERMINISTIC)
    assert len(result.reasons) <= 5


def test_falls_back_on_bad_json() -> None:
    llm = FakeLLMClient("not valid json at all")
    result, tokens = LLMClassificationAssist().classify(_ITEM, llm, _DETERMINISTIC)
    assert result is _DETERMINISTIC
    assert tokens > 0  # LLM call succeeded; tokens were spent even though parse failed


def test_falls_back_on_invalid_urgency_enum() -> None:
    llm = FakeLLMClient('{"urgency": "WRONG", "sender_taxonomy": "internal"}')
    result, tokens = LLMClassificationAssist().classify(_ITEM, llm, _DETERMINISTIC)
    assert result is _DETERMINISTIC
    assert tokens > 0  # LLM call succeeded; tokens were spent even though schema was invalid


def test_falls_back_on_network_error() -> None:
    class ErrorClient:
        def complete(self, *, system: str, user: str, max_tokens: int) -> LLMResponse:
            raise RuntimeError("network error")

    result, tokens = LLMClassificationAssist().classify(_ITEM, ErrorClient(), _DETERMINISTIC)
    assert result is _DETERMINISTIC
    assert tokens == 0


def test_confidence_score_set_on_llm_result() -> None:
    llm = FakeLLMClient('{"urgency": "high", "sender_taxonomy": "external_known", "reasons": []}')
    result, _ = LLMClassificationAssist().classify(_ITEM, llm, _DETERMINISTIC)
    assert result.confidence_score == 0.75


def test_prompt_contains_subject_and_excerpt() -> None:
    llm = FakeLLMClient('{"urgency": "low", "sender_taxonomy": "external_unknown", "reasons": []}')
    LLMClassificationAssist().classify(_ITEM, llm, _DETERMINISTIC)
    assert len(llm.calls) == 1
    user_prompt = str(llm.calls[0]["user"])
    assert "Urgent: Contract Review" in user_prompt
    assert "contract" in user_prompt


# ── DailyTokenBudget ──────────────────────────────────────────────────────────


def test_budget_starts_at_full_limit(tmp_path: Path) -> None:
    budget = DailyTokenBudget(tmp_path / "budget.json", daily_limit=500)
    assert budget.remaining() == 500
    assert budget.tokens_used_today() == 0


def test_budget_reduces_after_record(tmp_path: Path) -> None:
    budget = DailyTokenBudget(tmp_path / "budget.json", daily_limit=500)
    budget.record(200)
    assert budget.remaining() == 300
    assert budget.tokens_used_today() == 200


def test_budget_accumulates_across_records(tmp_path: Path) -> None:
    budget = DailyTokenBudget(tmp_path / "budget.json", daily_limit=1000)
    budget.record(300)
    budget.record(400)
    assert budget.tokens_used_today() == 700
    assert budget.remaining() == 300


def test_budget_clamps_to_zero(tmp_path: Path) -> None:
    budget = DailyTokenBudget(tmp_path / "budget.json", daily_limit=100)
    budget.record(200)
    assert budget.remaining() == 0


def test_budget_resets_on_new_date(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(json.dumps({"date": "2000-01-01", "tokens_used": 9999}))
    budget = DailyTokenBudget(path, daily_limit=500)
    assert budget.remaining() == 500
    assert budget.tokens_used_today() == 0


def test_budget_handles_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text("not json{{{")
    budget = DailyTokenBudget(path, daily_limit=500)
    assert budget.remaining() == 500
