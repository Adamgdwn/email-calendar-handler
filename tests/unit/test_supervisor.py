from src.agents.supervisor import EmailSupervisor


def test_supervisor_constructs_default_agent_topology() -> None:
    supervisor = EmailSupervisor.default()

    assert supervisor.classification_agent.system_prompt_budget_tokens == 400
    assert supervisor.filing_agent.system_prompt_budget_tokens == 600
