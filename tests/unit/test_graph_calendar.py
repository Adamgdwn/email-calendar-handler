"""Graph calendarView fetch and mapping: deterministic windows, lenient
participants, paging, cancellation, and typed errors. Fakes only."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.ingestion.graph_calendar import (
    CALENDAR_PAGE_SIZE,
    GraphCalendarError,
    GraphDateTimeTimeZone,
    GraphEventPayload,
    build_calendar_view_url,
    calendar_window_utc,
    fetch_calendar_events,
    map_graph_event,
)
from tests.fakes import ScriptedGraphTransport, graph_event

TODAY = date(2026, 7, 4)
SYNTHETIC_AUTH_VALUE = "synthetic-access-token"
PAGE_TWO = "https://graph.microsoft.com/v1.0/me/calendarView?skiptoken=synthetic-page-two"


def test_calendar_window_is_utc_midnight_aligned() -> None:
    start, end = calendar_window_utc(TODAY, 1)

    assert start == datetime(2026, 7, 3, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 6, 0, 0, tzinfo=UTC)


def test_calendar_window_rejects_days_below_one() -> None:
    with pytest.raises(ValueError, match="at least today"):
        calendar_window_utc(TODAY, 0)


def test_calendar_view_url_is_deterministic() -> None:
    start, end = calendar_window_utc(TODAY, 1)

    url = build_calendar_view_url(start, end)

    assert url.startswith("https://graph.microsoft.com/v1.0/me/calendarView?")
    assert "startDateTime=2026-07-03T00%3A00%3A00Z" in url
    assert "endDateTime=2026-07-06T00%3A00%3A00Z" in url
    assert f"%24top={CALENDAR_PAGE_SIZE}" in url


def test_seven_digit_fraction_is_trimmed_to_microseconds() -> None:
    value = GraphDateTimeTimeZone.model_validate(
        {"dateTime": "2026-07-04T16:00:00.1234567", "timeZone": "UTC"}
    )

    assert value.to_utc() == datetime(2026, 7, 4, 16, 0, 0, 123456, tzinfo=UTC)


def test_named_zone_converts_to_utc() -> None:
    value = GraphDateTimeTimeZone.model_validate(
        {"dateTime": "2026-07-04T10:00:00.0000000", "timeZone": "America/Edmonton"}
    )

    assert value.to_utc() == datetime(2026, 7, 4, 16, 0, tzinfo=UTC)


def test_unknown_zone_raises_calendar_error() -> None:
    value = GraphDateTimeTimeZone.model_validate(
        {"dateTime": "2026-07-04T10:00:00", "timeZone": "Synthetic/Nowhere"}
    )

    with pytest.raises(GraphCalendarError, match="Synthetic/Nowhere"):
        value.to_utc()


def test_map_graph_event_normalizes_participants_and_excerpt() -> None:
    payload = GraphEventPayload.model_validate(
        graph_event(
            "evt-0001",
            subject="Boiler inspection",
            attendees=("Owner@Example.com", "owner@example.com", "client@clientfirm.example"),
            location="Plant 4",
            join_url="https://teams.example/join/evt-0001",
            body="  Agenda:   review   pressure logs  " + "x" * 600,
        )
    )

    event = map_graph_event(payload)

    assert event.provider_event_id == "evt-0001"
    assert [a.email for a in event.attendees] == [
        "owner@example.com",
        "client@clientfirm.example",
    ]
    assert event.organizer is not None
    assert event.organizer.email == "organizer@clientfirm.example"
    assert event.location == "Plant 4"
    assert event.online_meeting_url == "https://teams.example/join/evt-0001"
    assert len(event.body_excerpt) == 500
    assert event.body_excerpt.startswith("Agenda: review pressure logs")


def test_room_placeholders_without_address_are_skipped() -> None:
    payload_dict = graph_event("evt-0002", attendees=("owner@example.com",))
    payload_dict["attendees"].append({"emailAddress": {"name": "Boardroom"}})
    payload_dict["attendees"].append({"emailAddress": {"address": "not-an-email"}})
    payload_dict["organizer"] = {}

    event = map_graph_event(GraphEventPayload.model_validate(payload_dict))

    assert [a.email for a in event.attendees] == ["owner@example.com"]
    assert event.organizer is None


def test_legacy_online_meeting_url_is_fallback_only() -> None:
    with_legacy = graph_event("evt-0003")
    with_legacy["onlineMeetingUrl"] = "https://legacy.example/join"
    event = map_graph_event(GraphEventPayload.model_validate(with_legacy))
    assert event.online_meeting_url == "https://legacy.example/join"

    both = graph_event("evt-0004", join_url="https://teams.example/preferred")
    both["onlineMeetingUrl"] = "https://legacy.example/join"
    event = map_graph_event(GraphEventPayload.model_validate(both))
    assert event.online_meeting_url == "https://teams.example/preferred"


def test_fetch_follows_paging_and_skips_cancelled() -> None:
    start, end = calendar_window_utc(TODAY, 1)
    first_url = build_calendar_view_url(start, end)
    cancelled = graph_event("evt-cancelled")
    cancelled["isCancelled"] = True
    transport = ScriptedGraphTransport(
        {
            first_url: {
                "value": [graph_event("evt-0001"), cancelled],
                "@odata.nextLink": PAGE_TWO,
            },
            PAGE_TWO: {"value": [graph_event("evt-0002")]},
        }
    )

    events = fetch_calendar_events(
        transport, access_token=SYNTHETIC_AUTH_VALUE, start=start, end=end
    )

    assert [event.provider_event_id for event in events] == ["evt-0001", "evt-0002"]
    assert transport.requested_urls == [first_url, PAGE_TWO]
    assert transport.seen_headers[0]["Authorization"] == f"Bearer {SYNTHETIC_AUTH_VALUE}"


def test_error_payload_raises_with_reconnect_hint() -> None:
    start, end = calendar_window_utc(TODAY, 1)
    transport = ScriptedGraphTransport(
        {
            build_calendar_view_url(start, end): {
                "error": {"code": "ErrorAccessDenied", "message": "missing scope"}
            }
        }
    )

    with pytest.raises(GraphCalendarError, match="inboxmind connect"):
        fetch_calendar_events(transport, access_token=SYNTHETIC_AUTH_VALUE, start=start, end=end)


def test_error_payload_without_hint_code_omits_reconnect_hint() -> None:
    start, end = calendar_window_utc(TODAY, 1)
    transport = ScriptedGraphTransport(
        {
            build_calendar_view_url(start, end): {
                "error": {"code": "SyntheticCode", "message": "synthetic detail"}
            }
        }
    )

    with pytest.raises(GraphCalendarError, match=r"SyntheticCode") as excinfo:
        fetch_calendar_events(transport, access_token=SYNTHETIC_AUTH_VALUE, start=start, end=end)
    assert "inboxmind connect" not in str(excinfo.value)
