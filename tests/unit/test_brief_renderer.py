from datetime import UTC, date, datetime

from src.brief.renderer import render_brief
from src.models.brief_models import (
    BriefThreadSummary,
    FilingAcceptanceStats,
    FilingProposal,
    MorningBrief,
)
from src.models.calendar_models import CalendarEvent, EventAttendee
from src.models.email_models import UrgencyBand


def make_brief(
    threads: list[BriefThreadSummary] | None = None,
    proposals: list[FilingProposal] | None = None,
    events: list[CalendarEvent] | None = None,
    acceptance: FilingAcceptanceStats | None = None,
) -> MorningBrief:
    return MorningBrief(
        brief_date=date(2026, 7, 4),
        account_email="owner@example.com",
        profile_id="consulting",
        persona_display_name="Consulting",
        lookback_hours=24,
        generated_at=datetime(2026, 7, 4, 6, 30, tzinfo=UTC),
        events=events or [],
        threads=threads or [],
        proposals=proposals or [],
        acceptance=acceptance or FilingAcceptanceStats(),
        classified_now=len(threads or []),
        previously_classified=0,
    )


def make_thread(thread_id: str, subject: str, urgency: UrgencyBand) -> BriefThreadSummary:
    return BriefThreadSummary(
        thread_id=thread_id,
        subject=subject,
        senders=["client@example.com"],
        profile_id="consulting",
        urgency=urgency,
        message_count=2,
        latest_at=datetime(2026, 7, 4, 6, 0, tzinfo=UTC),
    )


def test_renders_bands_in_priority_order_and_omits_empty_bands() -> None:
    threads = [
        make_thread("t-low", "Newsletter", UrgencyBand.LOW),
        make_thread("t-crit", "Contract deadline today", UrgencyBand.CRITICAL),
    ]

    markdown = render_brief(make_brief(threads=threads))

    assert markdown.startswith("# Morning Brief - 2026-07-04")
    assert markdown.index("## Critical") < markdown.index("## Low")
    assert "## High" not in markdown
    assert "## Normal" not in markdown
    assert "**Contract deadline today**" in markdown
    assert "2 messages" in markdown
    assert "[consulting]" in markdown
    assert "classified now" in markdown


def test_renders_proposals_with_stable_ids() -> None:
    proposal = FilingProposal(
        proposal_id="abc123def456",
        message_id="row-0001",
        subject="Contract deadline today",
        urgency=UrgencyBand.CRITICAL,
        proposed_path=["Review"],
        requires_review=True,
        rationale="No human-approved filing rule is available.",
    )

    markdown = render_brief(make_brief(proposals=[proposal]))

    assert "## Filing proposals" in markdown
    assert "`abc123def456`" in markdown
    assert "[critical] Contract deadline today -> Review" in markdown
    assert "inboxmind review" in markdown


def test_empty_brief_renders_calm_message() -> None:
    markdown = render_brief(make_brief())

    assert "No new mail in this window." in markdown
    assert "No filing proposals in this window." in markdown
    assert "## Critical" not in markdown


def make_event(
    subject: str = "Client review",
    *,
    is_all_day: bool = False,
    attendees: list[EventAttendee] | None = None,
    location: str | None = None,
    online_meeting_url: str | None = None,
) -> CalendarEvent:
    return CalendarEvent(
        provider_event_id="evt-0001",
        subject=subject,
        start=datetime(2026, 7, 4, 9, 0, tzinfo=UTC),
        end=datetime(2026, 7, 4, 9, 30, tzinfo=UTC),
        is_all_day=is_all_day,
        attendees=attendees or [],
        location=location,
        online_meeting_url=online_meeting_url,
    )


def test_agenda_renders_between_window_and_triage() -> None:
    markdown = render_brief(make_brief(events=[make_event()]))

    assert markdown.index("Window:") < markdown.index("## Agenda")
    assert markdown.index("## Agenda") < markdown.index("Triage:")
    assert "- 09:00-09:30 **Client review**" in markdown


def test_agenda_event_line_lists_people_location_and_join_link() -> None:
    attendees = [EventAttendee(email=f"person{i}@example.com") for i in range(6)]
    attendees[0] = EventAttendee(name="Casey Lee", email="casey@example.com")
    event = make_event(
        attendees=attendees,
        location="Plant 4",
        online_meeting_url="https://teams.example/join/1",
    )

    markdown = render_brief(make_brief(events=[event]))

    expected = (
        "with Casey Lee, person1@example.com, person2@example.com, person3@example.com +2 more"
    )
    assert expected in markdown
    assert "(Plant 4)" in markdown
    assert "join: https://teams.example/join/1" in markdown


def test_all_day_event_renders_without_times() -> None:
    markdown = render_brief(make_brief(events=[make_event("Site visit", is_all_day=True)]))

    assert "- All day: **Site visit**" in markdown


def test_empty_agenda_renders_no_meetings_line() -> None:
    markdown = render_brief(make_brief())

    assert "## Agenda" in markdown
    assert "No meetings today." in markdown


def test_boost_reason_appends_to_thread_line() -> None:
    thread = make_thread("t-boost", "Newsletter planning", UrgencyBand.NORMAL)
    boosted = thread.model_copy(
        update={"boost_reason": "boosted from low: meeting today with news@example.com"}
    )

    markdown = render_brief(make_brief(threads=[boosted]))

    assert "boosted from low: meeting today with news@example.com" in markdown


def test_footer_shows_no_feedback_when_empty() -> None:
    markdown = render_brief(make_brief())

    assert "## Filing feedback" in markdown
    assert "No filing feedback yet" in markdown


def test_footer_shows_acceptance_rate_and_open_gate() -> None:
    markdown = render_brief(make_brief(acceptance=FilingAcceptanceStats(total=10, accepted=8)))

    assert "Filing acceptance: 80% (8/10 reviewed)." in markdown
    assert "Write-scope gate (70%) is open." in markdown


def test_footer_reports_closed_gate_below_threshold() -> None:
    markdown = render_brief(make_brief(acceptance=FilingAcceptanceStats(total=10, accepted=6)))

    assert "Filing acceptance: 60% (6/10 reviewed)." in markdown
    assert "Write-scope gate (70%) is closed." in markdown
