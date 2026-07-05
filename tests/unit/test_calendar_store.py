"""Replace-window semantics for calendar_events against the in-memory gateway."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.memory.calendar_store import CALENDAR_EVENTS_TABLE, load_events, replace_window
from src.memory.supabase_client import SupabaseStoreError
from src.models.calendar_models import CalendarEvent, EventAttendee
from tests.fakes import FakeTableGateway

ACCOUNT_ID = "account-0001"
WINDOW_START = datetime(2026, 7, 3, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 7, 6, 0, 0, tzinfo=UTC)


def make_event(
    event_id: str, *, hour: int = 16, subject: str = "Synthetic meeting"
) -> CalendarEvent:
    start = datetime(2026, 7, 4, hour, 0, tzinfo=UTC)
    return CalendarEvent(
        provider_event_id=event_id,
        subject=subject,
        start=start,
        end=start + timedelta(minutes=30),
        organizer=EventAttendee(name="Organizer", email="organizer@clientfirm.example"),
        attendees=[EventAttendee(email="owner@example.com")],
        location="Plant 4",
        online_meeting_url="https://teams.example/join/1",
        body_excerpt="Agenda note",
    )


def store(gateway: FakeTableGateway, events: list[CalendarEvent], account: str = ACCOUNT_ID) -> int:
    return replace_window(
        gateway,
        account_id=account,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        events=events,
    )


def test_round_trip_preserves_fields_but_never_stores_body_text() -> None:
    gateway = FakeTableGateway()

    assert store(gateway, [make_event("evt-0001")]) == 1

    row = gateway.tables[CALENDAR_EVENTS_TABLE][0]
    assert "body_excerpt" not in row

    loaded = load_events(gateway, account_id=ACCOUNT_ID, start=WINDOW_START, end=WINDOW_END)
    assert len(loaded) == 1
    event = loaded[0]
    assert event.provider_event_id == "evt-0001"
    assert event.start == datetime(2026, 7, 4, 16, 0, tzinfo=UTC)
    assert event.organizer is not None
    assert event.organizer.email == "organizer@clientfirm.example"
    assert [a.email for a in event.attendees] == ["owner@example.com"]
    assert event.location == "Plant 4"
    assert event.online_meeting_url == "https://teams.example/join/1"
    assert event.body_excerpt == ""  # excerpts live in memory only, never in storage


def test_replace_prunes_stale_rows_in_window() -> None:
    gateway = FakeTableGateway()
    store(gateway, [make_event("evt-0001"), make_event("evt-0002", hour=18)])

    store(gateway, [make_event("evt-0001", subject="Moved standup")])

    rows = gateway.tables[CALENDAR_EVENTS_TABLE]
    assert len(rows) == 1
    assert rows[0]["provider_event_id"] == "evt-0001"
    assert rows[0]["subject"] == "Moved standup"


def test_event_moved_into_window_replaces_its_old_row() -> None:
    gateway = FakeTableGateway()
    outside = datetime(2026, 7, 10, 16, 0, tzinfo=UTC)
    gateway.insert_rows(
        CALENDAR_EVENTS_TABLE,
        [
            {
                "account_id": ACCOUNT_ID,
                "provider_event_id": "evt-0001",
                "subject": "Old date",
                "start_at": outside.isoformat(),
                "end_at": (outside + timedelta(minutes=30)).isoformat(),
                "is_all_day": False,
                "attendees": [],
            }
        ],
    )

    store(gateway, [make_event("evt-0001")])

    rows = gateway.tables[CALENDAR_EVENTS_TABLE]
    assert len(rows) == 1
    assert rows[0]["subject"] == "Synthetic meeting"


def test_empty_fetch_still_prunes_cancelled_meetings() -> None:
    gateway = FakeTableGateway()
    store(gateway, [make_event("evt-0001")])

    assert store(gateway, []) == 0
    assert gateway.tables[CALENDAR_EVENTS_TABLE] == []


def test_duplicate_provider_ids_collapse_last_wins() -> None:
    gateway = FakeTableGateway()

    stored = store(
        gateway,
        [make_event("evt-0001"), make_event("evt-0001", subject="Second write")],
    )

    assert stored == 1
    rows = gateway.tables[CALENDAR_EVENTS_TABLE]
    assert len(rows) == 1
    assert rows[0]["subject"] == "Second write"


def test_load_events_filters_window_sorts_and_scopes_by_account() -> None:
    gateway = FakeTableGateway()
    store(gateway, [make_event("evt-late", hour=18), make_event("evt-early", hour=9)])
    store(gateway, [make_event("evt-other")], account="account-0002")

    loaded = load_events(gateway, account_id=ACCOUNT_ID, start=WINDOW_START, end=WINDOW_END)
    assert [event.provider_event_id for event in loaded] == ["evt-early", "evt-late"]

    later_only = load_events(
        gateway,
        account_id=ACCOUNT_ID,
        start=datetime(2026, 7, 4, 17, 0, tzinfo=UTC),
        end=WINDOW_END,
    )
    assert [event.provider_event_id for event in later_only] == ["evt-late"]


def test_corrupt_stored_row_raises_typed_store_error() -> None:
    gateway = FakeTableGateway()
    start = datetime(2026, 7, 4, 16, 0, tzinfo=UTC)
    gateway.insert_rows(
        CALENDAR_EVENTS_TABLE,
        [
            {
                "account_id": ACCOUNT_ID,
                "provider_event_id": "evt-corrupt",
                "subject": "Backwards",
                "start_at": start.isoformat(),
                "end_at": (start - timedelta(hours=1)).isoformat(),
                "is_all_day": False,
                "attendees": [],
            }
        ],
    )

    with pytest.raises(SupabaseStoreError, match="evt-corrupt"):
        load_events(gateway, account_id=ACCOUNT_ID, start=WINDOW_START, end=WINDOW_END)
