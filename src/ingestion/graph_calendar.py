"""Read-only Microsoft Graph `calendarView` fetch and mapping to `CalendarEvent`.

The window is UTC-midnight aligned (`today +/- N days`), so the request URL is
deterministic for a given date and scripted transports can replay it. Requests
send no `Prefer: outlook.timezone`, so Graph returns event times in UTC.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator

from src.ingestion.graph_delta import GRAPH_BASE_URL, GraphTransport
from src.models.calendar_models import EVENT_EXCERPT_CHARS, CalendarEvent, EventAttendee

GRAPH_CALENDAR_SELECT_FIELDS = (
    "id",
    "subject",
    "start",
    "end",
    "isAllDay",
    "organizer",
    "attendees",
    "location",
    "onlineMeeting",
    "onlineMeetingUrl",
    "bodyPreview",
    "isCancelled",
)
CALENDAR_PAGE_SIZE = 50
_RECONNECT_HINT_CODES = ("ErrorAccessDenied", "Forbidden", "InvalidAuthenticationToken")
_FRACTION_PATTERN = re.compile(r"^(.*T\d{2}:\d{2}:\d{2})\.(\d+)(.*)$")


class GraphCalendarError(RuntimeError):
    """Raised when Microsoft Graph rejects or mangles a calendar request."""


def calendar_window_utc(today: date, days: int) -> tuple[datetime, datetime]:
    """[start of today-N, start of today+N+1) in UTC; N >= 1 covers every local timezone's today."""
    if days < 1:
        msg = "calendar window must cover at least today +/- 1 day"
        raise ValueError(msg)
    start = datetime.combine(today - timedelta(days=days), time.min, tzinfo=UTC)
    end = datetime.combine(today + timedelta(days=days + 1), time.min, tzinfo=UTC)
    return start, end


def build_calendar_view_url(start: datetime, end: datetime) -> str:
    params = {
        "startDateTime": _graph_instant(start),
        "endDateTime": _graph_instant(end),
        "$select": ",".join(GRAPH_CALENDAR_SELECT_FIELDS),
        "$top": str(CALENDAR_PAGE_SIZE),
    }
    return f"{GRAPH_BASE_URL}/me/calendarView?{urlencode(params)}"


class GraphDateTimeTimeZone(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    date_time: datetime = Field(alias="dateTime")
    time_zone: str = Field(default="UTC", alias="timeZone")

    @field_validator("date_time", mode="before")
    @classmethod
    def trim_graph_fraction(cls, value: object) -> object:
        """Graph emits 7-digit fractional seconds; trim to the microseconds Python parses."""
        if isinstance(value, str):
            match = _FRACTION_PATTERN.match(value)
            if match is not None:
                return f"{match.group(1)}.{match.group(2)[:6]}{match.group(3)}"
        return value

    def to_utc(self) -> datetime:
        value = self.date_time
        if value.tzinfo is None or value.utcoffset() is None:
            try:
                value = value.replace(tzinfo=ZoneInfo(self.time_zone))
            except (ZoneInfoNotFoundError, KeyError) as exc:
                msg = f"Microsoft Graph returned an unknown event time zone '{self.time_zone}'"
                raise GraphCalendarError(msg) from exc
        return value.astimezone(UTC)


class GraphEventEmail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    address: str | None = None


class GraphEventParticipant(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    email_address: GraphEventEmail | None = Field(default=None, alias="emailAddress")


class GraphEventLocation(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    display_name: str = Field(default="", alias="displayName")


class GraphOnlineMeeting(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    join_url: str | None = Field(default=None, alias="joinUrl")


class GraphEventPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    subject: str = ""
    start: GraphDateTimeTimeZone
    end: GraphDateTimeTimeZone
    is_all_day: bool = Field(default=False, alias="isAllDay")
    organizer: GraphEventParticipant | None = None
    attendees: list[GraphEventParticipant] = Field(default_factory=list)
    location: GraphEventLocation | None = None
    online_meeting: GraphOnlineMeeting | None = Field(default=None, alias="onlineMeeting")
    online_meeting_url: str | None = Field(default=None, alias="onlineMeetingUrl")
    body_preview: str = Field(default="", alias="bodyPreview")
    is_cancelled: bool = Field(default=False, alias="isCancelled")


class GraphCalendarPage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    value: list[dict[str, Any]] = Field(default_factory=list)
    next_link: HttpUrl | None = Field(default=None, alias="@odata.nextLink")


def fetch_calendar_events(
    transport: GraphTransport,
    *,
    access_token: str,
    start: datetime,
    end: datetime,
) -> list[CalendarEvent]:
    headers = {"Authorization": f"Bearer {access_token}"}
    next_url: str | None = build_calendar_view_url(start, end)
    events: list[CalendarEvent] = []
    while next_url is not None:
        payload = transport.get_json(next_url, headers)
        _raise_for_calendar_error(payload)
        page = GraphCalendarPage.model_validate(payload)
        for item in page.value:
            event_payload = GraphEventPayload.model_validate(item)
            if event_payload.is_cancelled:
                continue
            events.append(map_graph_event(event_payload))
        next_url = str(page.next_link) if page.next_link is not None else None
    return events


def map_graph_event(payload: GraphEventPayload) -> CalendarEvent:
    return CalendarEvent(
        provider_event_id=payload.id,
        subject=payload.subject or "",
        start=payload.start.to_utc(),
        end=payload.end.to_utc(),
        is_all_day=payload.is_all_day,
        organizer=_map_attendee(payload.organizer),
        attendees=_map_attendees(payload.attendees),
        location=_location_name(payload.location),
        online_meeting_url=_online_meeting_url(payload),
        body_excerpt=" ".join(payload.body_preview.split())[:EVENT_EXCERPT_CHARS],
    )


def _map_attendee(participant: GraphEventParticipant | None) -> EventAttendee | None:
    """Rooms and list placeholders can lack a usable address; skip them, never fail the event."""
    if participant is None or participant.email_address is None:
        return None
    address = participant.email_address.address
    if not address:
        return None
    try:
        return EventAttendee(name=participant.email_address.name, email=address)
    except ValidationError:
        return None


def _map_attendees(participants: list[GraphEventParticipant]) -> list[EventAttendee]:
    mapped: list[EventAttendee] = []
    seen: set[str] = set()
    for participant in participants:
        attendee = _map_attendee(participant)
        if attendee is not None and attendee.email not in seen:
            mapped.append(attendee)
            seen.add(attendee.email)
    return mapped


def _location_name(location: GraphEventLocation | None) -> str | None:
    if location is None or not location.display_name.strip():
        return None
    return location.display_name


def _online_meeting_url(payload: GraphEventPayload) -> str | None:
    if payload.online_meeting is not None and payload.online_meeting.join_url:
        return payload.online_meeting.join_url
    return payload.online_meeting_url


def _graph_instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _raise_for_calendar_error(payload: dict[str, Any]) -> None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return
    code = str(error.get("code") or "unknown")
    message = str(error.get("message") or "no detail")
    hint = ""
    if code in _RECONNECT_HINT_CODES:
        hint = " Re-run `inboxmind connect` to grant the Calendars.Read scope."
    msg = f"Microsoft Graph calendar request failed ({code}): {message}.{hint}"
    raise GraphCalendarError(msg)
