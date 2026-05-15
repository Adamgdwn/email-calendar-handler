from src.agents.supervisor import EmailSupervisor
from src.models.email_models import AccountContext, Provider


def test_supervisor_constructs_default_agent_topology() -> None:
    supervisor = EmailSupervisor.default()

    assert supervisor.classification_agent.system_prompt_budget_tokens == 400
    assert supervisor.filing_agent.system_prompt_budget_tokens == 600


def test_ingest_agent_requires_account_context() -> None:
    supervisor = EmailSupervisor.default()
    account_context = AccountContext(
        account_id="acct-graph",
        profile_id="prime_boilers",
        provider=Provider.MICROSOFT_GRAPH,
        display_name="Prime Boilers",
        primary_email="ops@primeboilers.example",
        org_type="commercial",
    )

    assert supervisor.ingest_agent.run(account_context) == []
