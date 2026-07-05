"""Persist and load calendar events for the agenda window.

Each sync replaces its whole window (delete + insert), so cancelled or moved
meetings never linger as stale agenda rows. Event bodies are not stored at
all: nothing downstream needs them yet, and the excerpt stays in memory only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.memory.supabase_client import SupabaseStoreError, TableGateway
from src.models.calendar_models import CalendarEvent, EventAttendee

CALENDAR_EVENTS_TABLE = "calendar_events"


def replace_window(
    gateway: TableGateway,
    *,
    account_id: str,
    window_start: datetime,
    window_end: datetime,
    events: list[CalendarEvent],
) -> int:
    """Store this window's events, pruning stale rows and rows for refetched event ids.

    Duplicate provider ids collapse last-wins so the batch insert can never
    trip the (account_id, provider_event_id) unique constraint mid-sync.
    """
    window = (
        ("start_at", window_start.astimezone(UTC).isoformat()),
        ("start_at", window_end.astimezone(UTC).isoformat()),
    )
    gateway.delete_rows(
        CALENDAR_EVENTS_TABLE, eq={"account_id": account_id}, gte=window[0], lt=window[1]
    )
    if not events:
        return 0
    deduped = list({event.provider_event_id: event for event in events}.values())
    event_ids = [event.provider_event_id for event in deduped]
    gateway.delete_rows(
        CALENDAR_EVENTS_TABLE,
        eq={"account_id": account_id},
        in_filter=("provider_event_id", event_ids),
    )
    now = datetime.now(tz=UTC).isoformat()
    gateway.insert_rows(
        CALENDAR_EVENTS_TABLE,
        [_event_row(account_id, event, now) for event in deduped],
    )
    return len(deduped)


def load_events(
    gateway: TableGateway,
    *,
    account_id: str,
    start: datetime,
    end: datetime,
) -> list[CalendarEvent]:
    """Events starting within [start, end), soonest first."""
    rows = gateway.select_rows(
        CALENDAR_EVENTS_TABLE,
        "provider_event_id,subject,start_at,end_at,is_all_day,organizer_name,"
        "organizer_email,attendees,location,online_meeting_url",
        eq={"account_id": account_id},
        gte=("start_at", start.astimezone(UTC).isoformat()),
        lt=("start_at", end.astimezone(UTC).isoformat()),
    )
    events = [_to_event(row) for row in rows]
    events.sort(key=lambda event: event.start)
    return events


def _event_row(account_id: str, event: CalendarEvent, now: str) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "provider_event_id": event.provider_event_id,
        "subject": event.subject,
        "start_at": event.start.astimezone(UTC).isoformat(),
        "end_at": event.end.astimezone(UTC).isoformat(),
        "is_all_day": event.is_all_day,
        "organizer_name": event.organizer.name if event.organizer else None,
        "organizer_email": str(event.organizer.email) if event.organizer else None,
        "attendees": [
            {"name": attendee.name, "email": str(attendee.email)} for attendee in event.attendees
        ],
        "location": event.location,
        "online_meeting_url": event.online_meeting_url,
        "updated_at": now,
    }


def _to_event(row: dict[str, Any]) -> CalendarEvent:
    organizer_email = row.get("organizer_email")
    attendees_value = row.get("attendees")
    attendees = attendees_value if isinstance(attendees_value, list) else []
    try:
        return CalendarEvent(
            provider_event_id=str(row.get("provider_event_id")),
            subject=str(row.get("subject") or ""),
            start=_instant(row.get("start_at")),
            end=_instant(row.get("end_at")),
            is_all_day=bool(row.get("is_all_day")),
            organizer=(
                EventAttendee(name=row.get("organizer_name"), email=str(organizer_email))
                if organizer_email
                else None
            ),
            attendees=[
                EventAttendee(name=entry.get("name"), email=str(entry.get("email")))
                for entry in attendees
                if isinstance(entry, dict) and entry.get("email")
            ],
            location=row.get("location") or None,
            online_meeting_url=row.get("online_meeting_url") or None,
        )
    except (ValidationError, ValueError) as exc:
        msg = f"stored calendar event '{row.get('provider_event_id')}' is invalid: {exc}"
        raise SupabaseStoreError(msg) from exc


def _instant(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
