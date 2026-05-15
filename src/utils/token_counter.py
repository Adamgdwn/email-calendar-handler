from __future__ import annotations


def approximate_token_count(text: str) -> int:
    """Cheap rough counter for budget guards before provider-specific tokenization."""

    return max(1, len(text.split()))


def fits_budget(text: str, budget_tokens: int) -> bool:
    return approximate_token_count(text) <= budget_tokens
