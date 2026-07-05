"""Provider-neutral calendar contracts for the read-only agenda pipeline.

`CalendarEvent` carries no full body: event text obeys the same 500-character
excerpt discipline as email, enforced here so no caller can widen it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

EVENT_EXCERPT_CHARS = 500


class EventAttendee(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = None
    email: EmailStr

    @field_validator("email")
    @classmethod
    def email_must_be_lowercase(cls, value: str) -> str:
        return value.lower()


class CalendarEvent(BaseModel):
    provider_event_id: str = Field(min_length=1)
    subject: str = ""
    start: datetime
    end: datetime
    is_all_day: bool = False
    organizer: EventAttendee | None = None
    attendees: list[EventAttendee] = Field(default_factory=list)
    location: str | None = None
    online_meeting_url: str | None = None
    body_excerpt: str = Field(default="", max_length=EVENT_EXCERPT_CHARS)

    @field_validator("start", "end")
    @classmethod
    def times_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "event times must be timezone-aware"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def end_must_not_precede_start(self) -> CalendarEvent:
        if self.end < self.start:
            msg = "event end must not precede start"
            raise ValueError(msg)
        return self

    def participant_emails(self) -> set[str]:
        """Every human on the invite, lowercased; used for meeting-aware triage."""
        emails = {attendee.email for attendee in self.attendees}
        if self.organizer is not None:
            emails.add(self.organizer.email)
        return emails
