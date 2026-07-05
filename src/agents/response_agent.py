"""Persona-toned reply draft agent.

Full thread body is permitted here — drafting is the one stage where body
context is needed. ResponseAgent never calls other agents, sends email, or
writes to the mailbox. human_approved stays False on every output.
"""

from __future__ import annotations

from src.llm.anthropic_client import LLMClient
from src.models.persona_models import DraftRequest, DraftResponse


class ResponseAgent:
    """Prepare human-reviewed draft suggestions from full thread context."""

    system_prompt_budget_tokens = 800
    retrieved_context_budget_tokens = 1_200
    max_response_tokens = 600

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    def run(self, request: DraftRequest) -> DraftResponse:
        if self._llm is None:
            msg = "ResponseAgent.run() requires an LLMClient; pass one to __init__"
            raise RuntimeError(msg)
        system = self._build_system_prompt(request)
        user = self._build_user_message(request)
        llm_response = self._llm.complete(
            system=system,
            user=user,
            max_tokens=self.max_response_tokens,
        )
        latest_subject = (
            request.thread_messages[-1].subject if request.thread_messages else "(no subject)"
        )
        return DraftResponse(
            thread_id=request.thread_id,
            subject_recommendation=f"Re: {latest_subject}",
            body=llm_response.text,
            suggested_send_timing="After human review",
            human_approved=False,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
        )

    def _build_system_prompt(self, request: DraftRequest) -> str:
        persona = request.persona
        constraints = "\n".join(f"- {c}" for c in persona.response_constraints)
        return (
            f"You are drafting an email reply for {persona.display_name}.\n"
            f"Tone: {persona.tone}.\n"
            f"Constraints:\n{constraints}\n"
            "Write a concise reply body only. "
            "No subject line. "
            "No sign-off unless the tone requires it. "
            "Output only the reply body text."
        )

    def _build_user_message(self, request: DraftRequest) -> str:
        if not request.thread_messages:
            return "Draft a polite acknowledgement for a thread with no messages."
        messages = request.thread_messages
        per_msg_budget = max(100, self.retrieved_context_budget_tokens // len(messages))
        lines = ["Thread context (most recent last):"]
        for msg in messages:
            words = msg.body_text.split()
            body_excerpt = (
                " ".join(words[:per_msg_budget]) + " …"
                if len(words) > per_msg_budget
                else msg.body_text
            )
            lines.append(
                f"\nFrom: {msg.sender_email}\nSubject: {msg.subject}\nBody: {body_excerpt}\n---"
            )
        lines.append("\nDraft a reply to the most recent message.")
        return "\n".join(lines)
