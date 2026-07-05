"""Thin Anthropic messages client with injectable fake for unit tests."""

from __future__ import annotations

from typing import Protocol

import anthropic
from anthropic.types import TextBlock
from pydantic import BaseModel


class LLMResponse(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, max_tokens: int) -> LLMResponse: ...


class AnthropicClient:
    """Budget-guarded wrapper around the Anthropic messages API."""

    model = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, *, system: str, user: str, max_tokens: int) -> LLMResponse:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = next((block.text for block in response.content if isinstance(block, TextBlock)), "")
        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


class FakeLLMClient:
    """Deterministic stand-in for unit tests; records prompts for assertion."""

    def __init__(self, response_text: str = "Thank you for reaching out.") -> None:
        self.response_text = response_text
        self.calls: list[dict[str, object]] = []

    def complete(self, *, system: str, user: str, max_tokens: int) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return LLMResponse(
            text=self.response_text,
            input_tokens=len(system.split()) + len(user.split()),
            output_tokens=len(self.response_text.split()),
        )
