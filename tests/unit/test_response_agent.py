"""Unit tests for ResponseAgent using the fake LLM client."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agents.response_agent import ResponseAgent
from src.llm.anthropic_client import FakeLLMClient
from src.models.persona_models import DraftRequest, PersonaProfile, ThreadMessage
from src.personas.loader import load_personas


@pytest.fixture
def consulting_persona() -> PersonaProfile:
    return load_personas()["consulting"]


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient("Happy to help with that proposal.")


def _make_request(
    persona: PersonaProfile, thread_messages: list[ThreadMessage] | None = None
) -> DraftRequest:
    return DraftRequest(
        account_id="acct-001",
        thread_id="thread-001",
        persona=persona,
        thread_messages=thread_messages or [],
    )


def _sample_message(subject: str = "Test subject", body: str = "Test body") -> ThreadMessage:
    return ThreadMessage(
        sender_email="client@firm.example",
        subject=subject,
        body_text=body,
        received_at=datetime.now(UTC),
    )


def test_draft_human_approved_always_false(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    draft = ResponseAgent(fake_llm).run(_make_request(consulting_persona))
    assert draft.human_approved is False


def test_draft_body_matches_llm_output(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    draft = ResponseAgent(fake_llm).run(_make_request(consulting_persona))
    assert draft.body == fake_llm.response_text


def test_draft_records_token_counts(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    draft = ResponseAgent(fake_llm).run(_make_request(consulting_persona))
    assert draft.input_tokens > 0
    assert draft.output_tokens > 0


def test_llm_receives_persona_tone_in_system_prompt(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    ResponseAgent(fake_llm).run(_make_request(consulting_persona))
    assert len(fake_llm.calls) == 1
    assert consulting_persona.tone in str(fake_llm.calls[0]["system"])


def test_llm_receives_thread_sender_in_user_prompt(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    messages = [_sample_message(subject="Proposal review", body="Can you send the updated deck?")]
    ResponseAgent(fake_llm).run(_make_request(consulting_persona, thread_messages=messages))
    assert "client@firm.example" in str(fake_llm.calls[0]["user"])
    assert "Proposal review" in str(fake_llm.calls[0]["user"])


def test_subject_recommendation_prefixed_with_re(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    messages = [_sample_message(subject="Contract deadline")]
    draft = ResponseAgent(fake_llm).run(_make_request(consulting_persona, thread_messages=messages))
    assert draft.subject_recommendation == "Re: Contract deadline"


def test_subject_recommendation_uses_latest_message(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    messages = [
        _sample_message(subject="First"),
        _sample_message(subject="Second"),
    ]
    draft = ResponseAgent(fake_llm).run(_make_request(consulting_persona, thread_messages=messages))
    assert draft.subject_recommendation == "Re: Second"


def test_response_constraints_in_system_prompt(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    ResponseAgent(fake_llm).run(_make_request(consulting_persona))
    system = str(fake_llm.calls[0]["system"])
    assert any(c in system for c in consulting_persona.response_constraints)


def test_empty_thread_produces_acknowledgement_prompt(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    ResponseAgent(fake_llm).run(_make_request(consulting_persona, thread_messages=[]))
    assert "acknowledge" in str(fake_llm.calls[0]["user"]).lower()


def test_max_response_tokens_passed_to_llm(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    ResponseAgent(fake_llm).run(_make_request(consulting_persona))
    assert fake_llm.calls[0]["max_tokens"] == ResponseAgent.max_response_tokens


def test_long_body_truncated_within_budget(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    long_body = " ".join(["word"] * 2000)
    messages = [_sample_message(body=long_body)]
    ResponseAgent(fake_llm).run(_make_request(consulting_persona, thread_messages=messages))
    user_prompt = str(fake_llm.calls[0]["user"])
    assert "…" in user_prompt


def test_thread_id_preserved_in_response(
    consulting_persona: PersonaProfile, fake_llm: FakeLLMClient
) -> None:
    request = DraftRequest(
        account_id="acct-001",
        thread_id="specific-thread-xyz",
        persona=consulting_persona,
    )
    draft = ResponseAgent(fake_llm).run(request)
    assert draft.thread_id == "specific-thread-xyz"
