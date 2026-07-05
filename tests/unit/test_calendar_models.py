"""Validation rules for the provider-neutral calendar contracts."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.models.calendar_models import EVENT_EXCERPT_CHARS, CalendarEvent, EventAttendee

START = datetime(2026, 7, 4, 16, 0, tzinfo=UTC)


def make_event(**overrides: object) -> CalendarEvent:
    payload: dict[str, object] = {
        "provider_event_id": "evt-0001",
        "subject": "Synthetic meeting",
        "start": START,
        "end": START + timedelta(minutes=30),
    }
    payload.update(overrides)
    return CalendarEvent.model_validate(payload)


def test_event_times_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_event(start=datetime(2026, 7, 4, 16, 0))


def test_event_end_must_not_precede_start() -> None:
    with pytest.raises(ValidationError, match="end must not precede start"):
        make_event(end=START - timedelta(minutes=1))


def test_zero_duration_event_is_allowed() -> None:
    assert make_event(end=START).end == START


def test_event_excerpt_obeys_email_discipline() -> None:
    assert make_event(body_excerpt="x" * EVENT_EXCERPT_CHARS).body_excerpt
    with pytest.raises(ValidationError):
        make_event(body_excerpt="x" * (EVENT_EXCERPT_CHARS + 1))


def test_provider_event_id_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        make_event(provider_event_id="")


def test_attendee_emails_are_lowercased() -> None:
    attendee = EventAttendee(name="Casey", email="Casey@Example.COM")
    assert attendee.email == "casey@example.com"


def test_participant_emails_union_organizer_and_attendees() -> None:
    event = make_event(
        organizer=EventAttendee(email="organizer@clientfirm.example"),
        attendees=[
            EventAttendee(email="owner@example.com"),
            EventAttendee(email="organizer@clientfirm.example"),
        ],
    )
    assert event.participant_emails() == {
        "organizer@clientfirm.example",
        "owner@example.com",
    }
