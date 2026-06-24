from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.ingestion.provider_contracts import (
    ProviderCheckpointKind,
    ProviderSyncCheckpoint,
    ProviderSyncResult,
)
from src.ingestion.thread_assembler import assemble_email_threads
from src.models.email_models import AccountContext, EmailAddress, Provider, RawEmail

AGENT_FILES = [
    Path("src/agents/classification_agent.py"),
    Path("src/agents/filing_agent.py"),
    Path("src/agents/relationship_agent.py"),
    Path("src/agents/response_agent.py"),
    Path("src/agents/learning_agent.py"),
]


def account_context(provider: Provider) -> AccountContext:
    return AccountContext(
        account_id=f"acct-{provider.value}",
        profile_id="prime_boilers",
        provider=provider,
        display_name="Prime Boilers",
        primary_email="ops@primeboilers.example",
        org_type="commercial",
    )


def raw_email(provider: Provider) -> RawEmail:
    return RawEmail(
        message_id=f"{provider.value}-message-1",
        thread_id=f"{provider.value}-thread-1",
        sender=EmailAddress(address="sender@example.com"),
        recipients=[EmailAddress(address="ops@primeboilers.example")],
        subject="Synthetic provider contract test",
        body_text="Synthetic body.",
        timestamp=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )


def test_graph_checkpoint_uses_delta_link_not_gmail_history_id() -> None:
    checkpoint = ProviderSyncCheckpoint(
        account_id="acct-graph",
        provider=Provider.MICROSOFT_GRAPH,
        graph_delta_link="https://graph.microsoft.com/v1.0/me/messages/delta?$deltatoken=abc",
    )

    assert checkpoint.kind == ProviderCheckpointKind.GRAPH_DELTA_LINK

    with pytest.raises(ValidationError):
        ProviderSyncCheckpoint(
            account_id="acct-graph",
            provider=Provider.MICROSOFT_GRAPH,
            gmail_history_id="123",
        )


def test_gmail_checkpoint_uses_history_id_not_graph_delta_link() -> None:
    checkpoint = ProviderSyncCheckpoint(
        account_id="acct-gmail",
        provider=Provider.GMAIL,
        gmail_history_id="123",
    )

    assert checkpoint.kind == ProviderCheckpointKind.GMAIL_HISTORY_ID

    with pytest.raises(ValidationError):
        ProviderSyncCheckpoint(
            account_id="acct-gmail",
            provider=Provider.GMAIL,
            graph_delta_link="https://graph.microsoft.com/v1.0/me/messages/delta?$deltatoken=abc",
        )


def test_provider_sync_result_uses_same_contracts_for_graph_and_gmail() -> None:
    for provider in (Provider.MICROSOFT_GRAPH, Provider.GMAIL):
        context = account_context(provider)
        email = raw_email(provider)
        threads = assemble_email_threads([email])
        checkpoint = ProviderSyncCheckpoint(
            account_id=context.account_id,
            provider=provider,
            graph_delta_link=(
                "https://graph.microsoft.com/v1.0/me/messages/delta?$deltatoken=abc"
                if provider == Provider.MICROSOFT_GRAPH
                else None
            ),
            gmail_history_id="123" if provider == Provider.GMAIL else None,
        )

        result = ProviderSyncResult(
            account_context=context,
            raw_emails=[email],
            threads=threads,
            checkpoint=checkpoint,
        )

        assert isinstance(result.raw_emails[0], RawEmail)
        assert result.threads[0].thread_id == email.thread_id
        assert result.account_context.provider == provider


def test_downstream_agents_do_not_branch_on_provider_constants() -> None:
    forbidden_provider_names = {provider.name for provider in Provider}
    forbidden_provider_values = {provider.value for provider in Provider}

    for path in AGENT_FILES:
        tree = ast.parse(path.read_text())
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        strings = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)}

        assert names.isdisjoint(forbidden_provider_names), path
        assert strings.isdisjoint(forbidden_provider_values), path
