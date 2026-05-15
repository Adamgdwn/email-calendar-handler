from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.ingestion.graph_mapper import (
    GraphMessagePayload,
    account_scoped_body_hash,
    dedupe_keys_for_email,
    detect_duplicate_email_keys,
    map_graph_message_to_raw_email,
)
from src.models.email_models import AccountContext, Provider, RawEmail

FIXTURE_PATH = Path("tests/fixtures/outlook_message.json")


@pytest.fixture
def account_context() -> AccountContext:
    return AccountContext(
        account_id="acct-prime",
        profile_id="prime_boilers",
        provider=Provider.MICROSOFT_GRAPH,
        display_name="Prime Boilers",
        primary_email="ops@primeboilers.example",
        org_type="commercial",
    )


def load_payload() -> GraphMessagePayload:
    return GraphMessagePayload.model_validate(json.loads(FIXTURE_PATH.read_text()))


def test_maps_graph_message_to_raw_email() -> None:
    email = map_graph_message_to_raw_email(load_payload())

    assert email.message_id == "AAMkADSyntheticMessage001"
    assert email.thread_id == "AAQkADSyntheticConversation001"
    assert email.sender.address == "alex.client@example.com"
    assert [recipient.address for recipient in email.recipients] == [
        "ops@primeboilers.example",
        "service@primeboilers.example",
    ]
    assert email.subject == "Boiler service follow-up"
    assert email.body_text == "Hello team, Please confirm the service window."
    assert email.timestamp.isoformat() == "2026-05-15T16:30:00+00:00"
    assert email.labels == ["Client", "Service"]


def test_graph_payload_requires_sender_or_from() -> None:
    payload = json.loads(FIXTURE_PATH.read_text())
    payload.pop("sender")
    payload.pop("from")

    with pytest.raises(ValidationError):
        GraphMessagePayload.model_validate(payload)


def test_graph_payload_requires_timezone_aware_received_time() -> None:
    payload = json.loads(FIXTURE_PATH.read_text())
    payload["receivedDateTime"] = "2026-05-15T16:30:00"

    with pytest.raises(ValidationError):
        GraphMessagePayload.model_validate(payload)


def test_body_hash_is_deterministic_and_account_scoped() -> None:
    body = "Synthetic body\r\n"

    assert account_scoped_body_hash("acct-1", body) == account_scoped_body_hash(
        "acct-1",
        "Synthetic body\n",
    )
    assert account_scoped_body_hash("acct-1", body) != account_scoped_body_hash(
        "acct-2",
        body,
    )


def test_dedupe_keys_detect_duplicate_message_ids(
    account_context: AccountContext,
) -> None:
    email = map_graph_message_to_raw_email(load_payload())
    duplicate = email.model_copy(update={"body_text": "Different body"})

    result = detect_duplicate_email_keys(
        [
            dedupe_keys_for_email(account_context, email),
            dedupe_keys_for_email(account_context, duplicate),
        ],
    )

    assert result.provider_message_ids == {"AAMkADSyntheticMessage001"}
    assert result.account_body_hashes == set()
    assert result.has_duplicates is True


def test_dedupe_keys_detect_duplicate_body_hashes_per_account(
    account_context: AccountContext,
) -> None:
    email = map_graph_message_to_raw_email(load_payload())
    duplicate_body = email.model_copy(update={"message_id": "AAMkADSyntheticMessage002"})
    different_account = AccountContext(
        account_id="acct-other",
        profile_id="prime_boilers",
        provider=Provider.MICROSOFT_GRAPH,
        display_name="Prime Boilers",
        primary_email="ops@primeboilers.example",
        org_type="commercial",
    )

    result = detect_duplicate_email_keys(
        [
            dedupe_keys_for_email(account_context, email),
            dedupe_keys_for_email(account_context, duplicate_body),
            dedupe_keys_for_email(different_account, duplicate_body),
        ],
    )

    assert result.provider_message_ids == set()
    assert result.account_body_hashes == {
        account_scoped_body_hash(account_context.account_id, email.body_text),
    }


def test_mapper_returns_raw_email_contract() -> None:
    email = map_graph_message_to_raw_email(load_payload())

    assert isinstance(email, RawEmail)
