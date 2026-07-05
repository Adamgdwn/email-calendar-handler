from __future__ import annotations

from datetime import UTC, datetime

from src.memory.account_store import ensure_account, upload_consents
from src.models.email_models import Provider
from tests.fakes import FakeTableGateway, make_consent


def create_account(gateway: FakeTableGateway) -> str:
    return ensure_account(
        gateway,
        provider=Provider.MICROSOFT_GRAPH,
        primary_email="owner@example.com",
        display_name="owner@example.com",
        org_type="organizational",
        scopes=["User.Read", "Mail.Read"],
    )


def test_ensure_account_bootstraps_persona_and_account_once() -> None:
    gateway = FakeTableGateway()

    first = create_account(gateway)
    second = create_account(gateway)

    assert first == second
    assert len(gateway.tables["personas"]) == 1
    assert len(gateway.tables["accounts"]) == 1
    account = gateway.tables["accounts"][0]
    assert account["persona_id"] == gateway.tables["personas"][0]["id"]
    assert account["provider"] == "microsoft_graph"
    assert account["scopes"] == ["User.Read", "Mail.Read"]


def test_upload_consents_skips_records_already_uploaded() -> None:
    gateway = FakeTableGateway()
    account_id = create_account(gateway)
    record = make_consent()

    assert upload_consents(gateway, account_id=account_id, records=[record]) == 1
    assert upload_consents(gateway, account_id=account_id, records=[record]) == 0

    assert len(gateway.tables["account_consents"]) == 1
    stored = gateway.tables["account_consents"][0]
    assert stored["account_id"] == account_id
    assert stored["human_confirmed"] is True
    assert stored["subject"] == "owner@example.com"


def test_upload_consents_uploads_new_grant_timestamps() -> None:
    gateway = FakeTableGateway()
    account_id = create_account(gateway)
    first = make_consent()
    later = make_consent(granted_at=datetime(2026, 7, 5, 9, 30, tzinfo=UTC))

    assert upload_consents(gateway, account_id=account_id, records=[first]) == 1
    assert upload_consents(gateway, account_id=account_id, records=[first, later]) == 1

    assert len(gateway.tables["account_consents"]) == 2
