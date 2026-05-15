from __future__ import annotations

from typing import Protocol

from src.models.filing_models import FilingRule


class FilingRuleReader(Protocol):
    def list_rules(self, account_id: str) -> list[FilingRule]:
        """Return filing rules scoped to one account."""


class InMemoryRuleStore:
    """Test-friendly read store; production writes belong to LearningAgent flows."""

    def __init__(self, rules: list[FilingRule] | None = None) -> None:
        self._rules = rules or []

    def list_rules(self, account_id: str) -> list[FilingRule]:
        return [rule for rule in self._rules if rule.account_id == account_id]
