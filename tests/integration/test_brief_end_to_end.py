"""Sync-then-brief integration: the first daily-value artifact from fake Graph mail."""

from datetime import UTC, datetime

from src.brief.renderer import render_brief
from src.brief_service import run_brief
from src.ingestion.graph_delta import build_initial_delta_url
from src.memory.calendar_store import replace_window
from src.models.calendar_models import CalendarEvent, EventAttendee
from src.models.email_models import UrgencyBand
from src.personas.loader import load_personas
from src.sync_service import run_sync
from src.utils.encryption import FieldEncryptor
from tests.fakes import (
    FakeTableGateway,
    ScriptedGraphTransport,
    empty_calendar_script,
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
            },
            **empty_calendar_script(),
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


def test_meeting_attendee_boosts_display_urgency_only() -> None:
    gateway, encryptor = synced_gateway()
    replace_window(
        gateway,
        account_id=str(gateway.rows("accounts")[0]["id"]),
        window_start=datetime(2026, 7, 4, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 7, 5, 0, 0, tzinfo=UTC),
        events=[
            CalendarEvent(
                provider_event_id="evt-boost",
                subject="Newsletter planning",
                start=datetime(2026, 7, 4, 17, 0, tzinfo=UTC),
                end=datetime(2026, 7, 4, 17, 30, tzinfo=UTC),
                organizer=EventAttendee(email="organizer@clientfirm.example"),
                attendees=[
                    EventAttendee(email="news@example.com"),
                    EventAttendee(email="owner@example.com"),
                ],
            )
        ],
    )

    brief = run_brief(
        gateway=gateway,
        encryptor=encryptor,
        personas=load_personas(),
        profile_override="prime_boilers",
        now=FIXED_NOW,
    )

    by_subject = {thread.subject: thread for thread in brief.threads}
    newsletter = by_subject["Community newsletter"]
    assert newsletter.urgency == UrgencyBand.NORMAL
    assert newsletter.boost_reason == "boosted from low: meeting today with news@example.com"
    assert by_subject["Emergency shutdown at plant 4"].boost_reason is None

    newsletter_row = next(
        row for row in gateway.rows("emails") if row["subject"] == "Community newsletter"
    )
    assert newsletter_row["urgency"] == "low"  # stored classification is never rewritten

    assert len(brief.events) == 1
    assert [a.email for a in brief.events[0].attendees] == ["news@example.com"]

    markdown = render_brief(brief)
    assert markdown.index("## Agenda") < markdown.index("Triage:")
    assert "- 17:00-17:30 **Newsletter planning**" in markdown
    assert "boosted from low: meeting today with news@example.com" in markdown
