from src.memory.rule_store import InMemoryRuleStore, SupabaseRuleStore
from src.models.filing_models import FilingRule, FilingRuleStatus
from tests.fakes import FakeTableGateway


def test_supabase_rule_store_maps_rows_to_typed_rules() -> None:
    gateway = FakeTableGateway()
    gateway.insert_rows(
        "filing_rules",
        [
            {
                "account_id": "acct-1",
                "path": ["Clients", "Example"],
                "status": "confirmed",
                "confidence_score": 0.95,
                "human_approved": True,
                "user_override": False,
            }
        ],
    )

    rules = SupabaseRuleStore(gateway).list_rules("acct-1")

    assert len(rules) == 1
    assert rules[0].rule_id == "row-0001"
    assert rules[0].path == ["Clients", "Example"]
    assert rules[0].status is FilingRuleStatus.CONFIRMED
    assert rules[0].human_approved is True


def test_supabase_rule_store_scopes_by_account() -> None:
    gateway = FakeTableGateway()
    gateway.insert_rows(
        "filing_rules",
        [
            {
                "account_id": "acct-other",
                "path": ["Elsewhere"],
                "status": "provisional",
                "confidence_score": 0.5,
                "human_approved": False,
                "user_override": False,
            }
        ],
    )

    assert SupabaseRuleStore(gateway).list_rules("acct-1") == []


def test_in_memory_rule_store_scopes_by_account() -> None:
    rule = FilingRule(
        rule_id="rule-1",
        account_id="acct-1",
        path=["Clients"],
        status=FilingRuleStatus.CONFIRMED,
        confidence_score=0.9,
    )
    store = InMemoryRuleStore([rule])

    assert store.list_rules("acct-1") == [rule]
    assert store.list_rules("acct-2") == []
