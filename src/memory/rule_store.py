"""Read and LearningAgent-approved write access to `filing_rules`.

Per module policy, all filing-rule reads go through this store, and the only
sanctioned write path is `save_rules` - invoked by the review flow after
`LearningAgent.run` reconciles feedback into rule statuses. Rows are always
stamped `created_by = 'learning_agent'`, matching the schema check constraint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from src.memory.supabase_client import TableGateway
from src.models.filing_models import FilingRule

FILING_RULES_TABLE = "filing_rules"
LEARNING_AGENT_WRITER = "learning_agent"


class FilingRuleReader(Protocol):
    def list_rules(self, account_id: str) -> list[FilingRule]:
        """Return filing rules scoped to one account."""


class InMemoryRuleStore:
    """Test-friendly read/write store; production writes belong to LearningAgent flows."""

    def __init__(self, rules: list[FilingRule] | None = None) -> None:
        self._rules = rules or []

    def list_rules(self, account_id: str) -> list[FilingRule]:
        return [rule for rule in self._rules if rule.account_id == account_id]

    def save_rules(self, account_id: str, rules: list[FilingRule]) -> int:
        del account_id  # rules already carry their own account_id
        by_id = {rule.rule_id: rule for rule in self._rules}
        for rule in rules:
            by_id[rule.rule_id] = rule
        self._rules = list(by_id.values())
        return len(rules)


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

    def save_rules(self, account_id: str, rules: list[FilingRule]) -> int:
        """The only sanctioned `filing_rules` writer; call it after LearningAgent.run.

        Rules already persisted (their `rule_id` is a stored row id) are updated
        in place so promotions preserve `human_approved`; freshly learned rules
        are inserted without an id so Postgres mints the uuid.
        """
        if not rules:
            return 0
        existing_ids = {
            str(row.get("id"))
            for row in self._gateway.select_rows(
                FILING_RULES_TABLE, "id", eq={"account_id": account_id}
            )
        }
        for rule in rules:
            payload = _rule_payload(rule)
            if rule.rule_id in existing_ids:
                self._gateway.update_rows(FILING_RULES_TABLE, payload, eq={"id": rule.rule_id})
            else:
                self._gateway.insert_rows(FILING_RULES_TABLE, [payload])
        return len(rules)


def _rule_payload(rule: FilingRule) -> dict[str, Any]:
    return {
        "account_id": rule.account_id,
        "path": rule.path,
        "match_criteria": {"path": "/".join(rule.path)},
        "status": rule.status.value,
        "confidence_score": rule.confidence_score,
        "human_approved": rule.human_approved,
        "user_override": rule.user_override,
        "created_by": LEARNING_AGENT_WRITER,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }


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
