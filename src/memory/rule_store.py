"""Read access to `filing_rules` for agents.

Per module policy, all filing-rule reads go through this store. Write paths
belong exclusively to LearningAgent-approved flows and arrive in chunk 11.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.memory.supabase_client import TableGateway
from src.models.filing_models import FilingRule

FILING_RULES_TABLE = "filing_rules"


class FilingRuleReader(Protocol):
    def list_rules(self, account_id: str) -> list[FilingRule]:
        """Return filing rules scoped to one account."""


class InMemoryRuleStore:
    """Test-friendly read store; production writes belong to LearningAgent flows."""

    def __init__(self, rules: list[FilingRule] | None = None) -> None:
        self._rules = rules or []

    def list_rules(self, account_id: str) -> list[FilingRule]:
        return [rule for rule in self._rules if rule.account_id == account_id]


class SupabaseRuleStore:
    """Reads `filing_rules` rows through the table gateway, typed on the way out."""

    def __init__(self, gateway: TableGateway) -> None:
        self._gateway = gateway

    def list_rules(self, account_id: str) -> list[FilingRule]:
        rows = self._gateway.select_rows(
            FILING_RULES_TABLE,
            "id,account_id,path,status,confidence_score,human_approved,user_override",
            eq={"account_id": account_id},
        )
        return [_to_rule(row) for row in rows]


def _to_rule(row: dict[str, Any]) -> FilingRule:
    return FilingRule.model_validate(
        {
            "rule_id": str(row.get("id")),
            "account_id": str(row.get("account_id")),
            "path": row.get("path"),
            "status": row.get("status"),
            "confidence_score": row.get("confidence_score"),
            "human_approved": row.get("human_approved"),
            "user_override": row.get("user_override"),
        }
    )
