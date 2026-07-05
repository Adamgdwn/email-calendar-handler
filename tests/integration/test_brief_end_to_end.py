"""Sync-then-brief integration: the first daily-value artifact from fake Graph mail."""

from datetime import UTC, datetime

from src.brief_service import run_brief
from src.ingestion.graph_delta import build_initial_delta_url
from src.models.email_models import UrgencyBand
from src.personas.loader import load_personas
from src.sync_service import run_sync
from src.utils.encryption import FieldEncryptor
from tests.fakes import (
    FakeTableGateway,
    ScriptedGraphTransport,
    graph_message,
    make_consent,
    make_token,
)

INITIAL_URL = build_initial_delta_url()
DELTA_LINK = "https://graph.microsoft.com/v1.0/delta?token=one"
FIXED_NOW = datetime(2026, 7, 4, 16, 0, 0, tzinfo=UTC)


def synced_gateway() -> tuple[FakeTableGateway, FieldEncryptor]:
    gateway = FakeTableGateway()
    encryptor = FieldEncryptor(FieldEncryptor.generate_key())
    transport = ScriptedGraphTransport(
        {
            INITIAL_URL: {
                "value": [
                    graph_message(
                        "m-0001",
                        conversation_id="conv-0001",
                        subject="Emergency shutdown at plant 4",
                        body="The site boiler needs attention now.",
                        received="2026-07-04T15:00:00Z",
                    ),
                    graph_message(
                        "m-0002",
                        conversation_id="conv-0002",
                        subject="Community newsletter",
                        body="Nothing that needs action.",
                        received="2026-07-04T14:00:00Z",
                        sender="news@example.com",
                    ),
                ],
                "@odata.deltaLink": DELTA_LINK,
            }
        }
    )
    run_sync(
        token=make_token(),
        transport=transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[make_consent()],
    )
    return gateway, encryptor


def test_sync_then_brief_classifies_persists_and_summarizes() -> None:
    gateway, encryptor = synced_gateway()

    brief = run_brief(
        gateway=gateway,
        encryptor=encryptor,
        personas=load_personas(),
        profile_override="prime_boilers",
        now=FIXED_NOW,
    )

    assert brief.classified_now == 2
    assert brief.previously_classified == 0
    assert brief.profile_id == "prime_boilers"

    bands = {thread.subject: thread.urgency for thread in brief.threads}
    assert bands == {
        "Emergency shutdown at plant 4": UrgencyBand.CRITICAL,
        "Community newsletter": UrgencyBand.LOW,
    }
    assert brief.threads[0].urgency == UrgencyBand.CRITICAL

    assert len(brief.proposals) == 2
    assert all(proposal.requires_review for proposal in brief.proposals)
    assert all(proposal.proposed_path == ["Review"] for proposal in brief.proposals)

    emails = gateway.rows("emails")
    assert {row["urgency"] for row in emails} == {"critical", "low"}
    assert all(row["classification"]["message_id"] == row["id"] for row in emails)

    prime_row = next(
        row for row in gateway.rows("personas") if row["profile_id"] == "prime_boilers"
    )
    assert gateway.rows("accounts")[0]["persona_id"] == prime_row["id"]


def test_second_brief_is_idempotent_with_stable_proposal_ids() -> None:
    gateway, encryptor = synced_gateway()
    personas = load_personas()

    first = run_brief(
        gateway=gateway,
        encryptor=encryptor,
        personas=personas,
        profile_override="prime_boilers",
        now=FIXED_NOW,
    )
    second = run_brief(
        gateway=gateway,
        encryptor=encryptor,
        personas=personas,
        now=FIXED_NOW,
    )

    assert second.classified_now == 0
    assert second.previously_classified == 2
    assert second.profile_id == "prime_boilers"  # persisted persona link, no flag needed
    assert [p.proposal_id for p in first.proposals] == [p.proposal_id for p in second.proposals]
