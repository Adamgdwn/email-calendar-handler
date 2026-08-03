"""Unit tests for AuditSynthesizer using the fake LLM client."""

from __future__ import annotations

import json

import pytest

from src.inbox_audit.audit_synthesizer import AuditSynthesisError, AuditSynthesizer
from src.llm.anthropic_client import FakeLLMClient
from src.models.audit_models import ClusterSummary


def _make_summary(account_email: str = "user@example.com") -> ClusterSummary:
    return ClusterSummary(
        account_email=account_email,
        months_scanned=12,
        total_messages=100,
        total_folders=5,
        current_folder_tree=[],
        domain_clusters=[],
        folder_utilization={},
        subject_keyword_clusters=[],
    )


def _valid_proposal_json(account_email: str = "user@example.com") -> str:
    return json.dumps(
        {
            "proposed_tree": [
                {
                    "path": ["Clients"],
                    "rationale": "All client emails",
                    "source_folders": ["Inbox/Clients"],
                    "estimated_volume": 50,
                }
            ],
            "folders_to_retire": ["OldClients"],
            "folders_to_keep": ["Inbox"],
            "key_changes": ["Consolidated client folders"],
            "implementation_note": "Move manually.",
        }
    )


def test_synthesize_returns_proposal() -> None:
    fake_llm = FakeLLMClient(_valid_proposal_json())
    proposal, _ = AuditSynthesizer(fake_llm).synthesize(_make_summary())
    assert len(proposal.proposed_tree) == 1
    assert proposal.proposed_tree[0].path == ["Clients"]


def test_synthesize_injects_account_email() -> None:
    fake_llm = FakeLLMClient(_valid_proposal_json())
    proposal, _ = AuditSynthesizer(fake_llm).synthesize(_make_summary("test@work.com"))
    assert proposal.account_email == "test@work.com"


def test_synthesize_returns_llm_response_with_token_counts() -> None:
    fake_llm = FakeLLMClient(_valid_proposal_json())
    _, response = AuditSynthesizer(fake_llm).synthesize(_make_summary())
    assert response.input_tokens > 0
    assert response.output_tokens > 0


def test_synthesize_passes_account_email_in_user_prompt() -> None:
    fake_llm = FakeLLMClient(_valid_proposal_json())
    AuditSynthesizer(fake_llm).synthesize(_make_summary("myaccount@firm.com"))
    assert "myaccount@firm.com" in str(fake_llm.calls[0]["user"])


def test_synthesize_raises_on_invalid_json() -> None:
    fake_llm = FakeLLMClient("this is not json at all")
    with pytest.raises(AuditSynthesisError, match="non-JSON"):
        AuditSynthesizer(fake_llm).synthesize(_make_summary())


def test_synthesize_raises_on_schema_mismatch() -> None:
    bad_json = json.dumps({"wrong_field": "oops"})
    fake_llm = FakeLLMClient(bad_json)
    with pytest.raises(AuditSynthesisError, match="schema"):
        AuditSynthesizer(fake_llm).synthesize(_make_summary())


def test_synthesize_raises_on_non_object_json() -> None:
    fake_llm = FakeLLMClient('["not", "an", "object"]')
    with pytest.raises(AuditSynthesisError):
        AuditSynthesizer(fake_llm).synthesize(_make_summary())


def test_synthesize_strips_markdown_fences() -> None:
    fenced = f"```json\n{_valid_proposal_json()}\n```"
    fake_llm = FakeLLMClient(fenced)
    proposal, _ = AuditSynthesizer(fake_llm).synthesize(_make_summary())
    assert proposal.proposed_tree[0].path == ["Clients"]


def test_synthesize_system_prompt_contains_constraints() -> None:
    fake_llm = FakeLLMClient(_valid_proposal_json())
    AuditSynthesizer(fake_llm).synthesize(_make_summary())
    system = str(fake_llm.calls[0]["system"])
    assert "3 levels" in system or "depth" in system.lower()
    assert "15" in system or "top-level" in system.lower()


def test_synthesize_uses_max_tokens_2000() -> None:
    fake_llm = FakeLLMClient(_valid_proposal_json())
    AuditSynthesizer(fake_llm).synthesize(_make_summary())
    assert fake_llm.calls[0]["max_tokens"] == 2_000
