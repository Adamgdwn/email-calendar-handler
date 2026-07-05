# 2026-07-04 - Chunk 10 Completion Plan: Calendar Read (Hardened Handoff)

This document finishes chunk 10 ("Calendar Read — Agenda In The Brief") from
`docs/production-instructions.md`. It was produced by auditing the half-built
state on branch `codex/chunk-10-calendar-read` against the actual code on
disk. Every anchor below was verified on 2026-07-04.

`docs/production-instructions.md` (chunk 10 section and Current
Recommendation) routes here; this plan is the single source of truth for
finishing the chunk.

## Execution contract (read first)

- Work the phases **strictly in order**. Each phase ends with a checkpoint
  command whose expected result is stated. Do not continue past a failing
  checkpoint.
- Edits are given as exact find/replace pairs or full new-file contents.
  If a find-anchor does not match the file, **stop and report** — do not
  improvise a similar edit.
- Only touch the files this plan names. Do not "improve" anything else.
- Run `bash scripts/governance-preflight.sh` once at the start of the session.
- After editing code in any phase, run `uv run ruff format` (no `--check`) to
  settle formatting before the checkpoint.
- Never print secrets. Never use real mailbox or calendar data. All fixtures
  stay synthetic.
- Ruff has bandit (`S`) rules on. In tests, never pass a string literal as
  `access_token=...` — define `SYNTHETIC_AUTH_VALUE = "synthetic-access-token"`
  at module top and pass the constant (this is the existing pattern in
  `tests/unit/test_graph_delta.py`). Line length limit is 100.

## Current verified state

Branch `codex/chunk-10-calendar-read` (created from main at cf64541).
Already implemented, reviewed, lint- and mypy-clean — **do not rewrite**:

- `src/models/calendar_models.py` — `CalendarEvent`, `EventAttendee`,
  `EVENT_EXCERPT_CHARS = 500`, tz-aware validators, `participant_emails()`.
- `src/ingestion/graph_calendar.py` — `calendar_window_utc`,
  `build_calendar_view_url`, Graph payload models, `fetch_calendar_events`
  (paging, cancelled-skip, error mapping with reconnect hint),
  `map_graph_event`, `GraphCalendarError`.
- `src/ingestion/graph_auth.py` — `GRAPH_REQUIRED_SCOPES` now includes
  `Calendars.Read`; the `.ReadWrite` fragment guard already rejects
  `Calendars.ReadWrite`.
- `src/memory/supabase_client.py` — `TableGateway` protocol + Supabase
  implementation gained `lt` filtering and `delete_rows`.
- `src/memory/calendar_store.py` — `replace_window` / `load_events`
  (gets one small hardening edit in Phase B).
- `supabase/schema.sql` — `calendar_events` table exists (index/RLS/policy
  still missing; Phase B).
- `tests/fakes.py` — `delete_rows`, `_compare_bound`, `graph_event`,
  `todays_calendar_url`, `empty_calendar_script`; `make_token` already
  includes `Calendars.Read` (fixed-date hardening edit in Phase B).

Baseline check results (2026-07-04): `ruff format --check`, `ruff check`,
`mypy` all pass; `pytest` has exactly **4 failures**, all in
`tests/unit/test_graph_token_cache.py`, caused by `Calendars.Read` joining
`GRAPH_REQUIRED_SCOPES`. Phase A fixes them. `secret_scan` passes.

## Design decisions locked by this plan (do not relitigate)

1. **Mail first, calendar second.** The calendar fetch runs only after the
   mail delta checkpoint is saved, so a calendar failure never loses mail
   progress. A calendar failure exits 1 with the reconnect hint — loud beats
   silent for a missing-scope misconfiguration.
2. **Replace-window storage.** Each sync deletes the fetched window plus any
   rows matching refetched event ids, then inserts fresh. No upserts.
   Duplicate provider ids collapse last-wins before insert so the
   `(account_id, provider_event_id)` unique constraint can never fail a sync.
3. **Event bodies are never persisted.** `body_excerpt` (max 500 chars) lives
   in memory only; the store neither writes nor reads it.
4. **Agenda selection = overlap, not starts-today.** An event is on today's
   agenda when its `[start, end)` range overlaps today's account-timezone
   day. This surfaces cross-midnight meetings and all-day invites created in
   other time zones (a starts-today filter silently drops a Toronto all-day
   invite for an Edmonton account). Trade-off accepted: a foreign-timezone
   all-day event may also appear on a neighboring day.
5. **Boost is a display-time overlay.** Stored classifications are never
   rewritten. A thread whose any-sender (lowercased) appears in today's
   attendee set is lifted one band (capped at critical), and `boost_reason`
   is set **only when the band actually changes**. Reason format, exactly:
   `boosted from {base.value}: meeting today with {sender}`. The attendee set
   excludes the account's own email. Filing proposals keep stored urgency.
6. **Deterministic test URLs.** `run_sync` computes the calendar window from
   `datetime.now(tz=UTC).date()`; fakes compute the identical URL via
   `todays_calendar_url()`. Sync-test event fixtures must use **real-today**
   dynamic dates (Phase B) so replace-window pruning is actually exercised on
   every run date, not just around 2026-07-04.

---

## Phase A — Repair the baseline (scope-change fallout)

### A1. `tests/unit/test_graph_token_cache.py` — 4 assertion updates

Replace **all 4** occurrences of:

```python
== ["User.Read", "Mail.Read"]
```

with:

```python
== ["User.Read", "Mail.Read", "Calendars.Read"]
```

They are on lines 142, 163, 181, 197 (`msal_request_scopes(...)`,
`fake.device_scopes` twice, `fake.silent_scopes`). Do **not** touch line 160's
tuple assertion `result.scopes == ("User.Read", "Mail.Read")` (it checks the
parsed token *response*, whose fixture stays `"User.Read Mail.Read"`), and do
not touch the `"scope"` string on line 32 of that file.

### A2. `tests/unit/test_graph_auth.py` — two new tests

Append at end of file:

```python
def test_required_scopes_include_read_only_calendar() -> None:
    assert "Calendars.Read" in GRAPH_REQUIRED_SCOPES


def test_graph_oauth_settings_reject_write_capable_calendar_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_graph_env(monkeypatch)
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")

    with pytest.raises(ValidationError, match="Calendars.ReadWrite"):
        MicrosoftGraphOAuthSettings(scopes=(*GRAPH_REQUIRED_SCOPES, "Calendars.ReadWrite"))
```

### Checkpoint A

```bash
uv run pytest -q
```

Expected: **0 failed** (121 passed).

---

## Phase B — Storage layer hardening + its unit tests

### B1. `supabase/schema.sql` — three missing statements

(1) After the line
`create index if not exists idx_emails_classification on emails using gin (classification);`
insert:

```sql
create index if not exists idx_calendar_events_account_start
  on calendar_events(account_id, start_at);
```

(2) After the line `alter table emails enable row level security;` insert:

```sql
alter table calendar_events enable row level security;
```

(3) After the line
`create policy "service_role_all_emails" on emails for all using (auth.role() = 'service_role');`
insert:

```sql
create policy "service_role_all_calendar_events"
  on calendar_events for all using (auth.role() = 'service_role');
```

### B2. `tests/fakes.py` — dynamic event dates (defuses a time-bomb)

The current `graph_event` defaults are frozen at 2026-07-04. Sync tests that
prove replace-window pruning rely on the events falling inside the
real-today window `run_sync` computes — with fixed dates those tests would
silently stop testing pruning after 2026-07-05.

Find:

```python
def graph_event(
    event_id: str,
    *,
    subject: str = "Synthetic meeting",
    start: str = "2026-07-04T16:00:00.0000000",
    end: str = "2026-07-04T16:30:00.0000000",
```

Replace with:

```python
def todays_event_time(hour: int, minute: int = 0) -> str:
    """A Graph-style dateTime (7-digit fraction) on real today, UTC.

    Sync tests must use real-today instants so replace-window pruning stays
    exercised on every run date instead of only around 2026-07-04.
    """
    moment = datetime.now(tz=UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.0000000")


def graph_event(
    event_id: str,
    *,
    subject: str = "Synthetic meeting",
    start: str | None = None,
    end: str | None = None,
```

Then find:

```python
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
```

Replace with:

```python
        "start": {"dateTime": start or todays_event_time(16), "timeZone": "UTC"},
        "end": {"dateTime": end or todays_event_time(16, 30), "timeZone": "UTC"},
```

Leave `make_consent` unchanged (its scopes list is a historical record;
nothing asserts calendar there).

### B3. `src/memory/calendar_store.py` — duplicate-id dedupe (last wins)

Find:

```python
    """Store this window's events, pruning stale rows and rows for refetched event ids."""
```

Replace with:

```python
    """Store this window's events, pruning stale rows and rows for refetched event ids.

    Duplicate provider ids collapse last-wins so the batch insert can never
    trip the (account_id, provider_event_id) unique constraint mid-sync.
    """
```

Find:

```python
    if not events:
        return 0
    event_ids = [event.provider_event_id for event in events]
```

Replace with:

```python
    if not events:
        return 0
    deduped = list({event.provider_event_id: event for event in events}.values())
    event_ids = [event.provider_event_id for event in deduped]
```

Find:

```python
    gateway.insert_rows(
        CALENDAR_EVENTS_TABLE,
        [_event_row(account_id, event, now) for event in events],
    )
    return len(events)
```

Replace with:

```python
    gateway.insert_rows(
        CALENDAR_EVENTS_TABLE,
        [_event_row(account_id, event, now) for event in deduped],
    )
    return len(deduped)
```

### B4. New file `tests/unit/test_calendar_models.py`

```python
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
```

### B5. New file `tests/unit/test_graph_calendar.py`

```python
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
```

### B6. New file `tests/unit/test_calendar_store.py`

```python
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
```

### Checkpoint B

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest -q
```

Expected: all pass, 0 failed.

---

## Phase C — Sync wiring + sync/CLI test updates

### C1. `src/sync_service.py`

(1) Imports — find:

```python
from pydantic import BaseModel, ValidationError

from src.ingestion.graph_delta import (
```

Replace with:

```python
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from src.ingestion.graph_calendar import calendar_window_utc, fetch_calendar_events
from src.ingestion.graph_delta import (
```

(2) Find:

```python
from src.memory.account_store import DEFAULT_PROFILE_ID, ensure_account, upload_consents
from src.memory.checkpoint_store import CheckpointStore
```

Replace with:

```python
from src.memory.account_store import DEFAULT_PROFILE_ID, ensure_account, upload_consents
from src.memory.calendar_store import replace_window
from src.memory.checkpoint_store import CheckpointStore
```

(3) Find:

```python
class SyncReport(BaseModel):
```

Replace with:

```python
DEFAULT_CALENDAR_DAYS = 1


class SyncReport(BaseModel):
```

(4) Find:

```python
    consents_uploaded: int
```

Replace with:

```python
    consents_uploaded: int
    calendar_days: int
    calendar_events_stored: int
```

(5) Find:

```python
    mail_folder_id: str = DEFAULT_MAIL_FOLDER_ID,
) -> SyncReport:
```

Replace with:

```python
    mail_folder_id: str = DEFAULT_MAIL_FOLDER_ID,
    calendar_days: int = DEFAULT_CALENDAR_DAYS,
) -> SyncReport:
```

(6) Find:

```python
    return SyncReport(
        account_email=token.subject,
```

Replace with:

```python
    calendar_events_stored = _sync_calendar(transport, token, gateway, account_id, calendar_days)
    return SyncReport(
        account_email=token.subject,
```

(7) Find:

```python
        consents_uploaded=consents_uploaded,
    )
```

Replace with:

```python
        consents_uploaded=consents_uploaded,
        calendar_days=calendar_days,
        calendar_events_stored=calendar_events_stored,
    )
```

(8) Append at end of file:

```python
def _sync_calendar(
    transport: GraphTransport,
    token: GraphTokenResult,
    gateway: TableGateway,
    account_id: str,
    calendar_days: int,
) -> int:
    """Mail is the critical path: this runs only after the delta checkpoint
    is saved, so a calendar failure never loses mail progress."""
    window_start, window_end = calendar_window_utc(datetime.now(tz=UTC).date(), calendar_days)
    events = retry_provider_call(
        lambda: fetch_calendar_events(
            transport,
            access_token=token.access_token.get_secret_value(),
            start=window_start,
            end=window_end,
        ),
        retry_exception_types=(GraphTransportError,),
    )
    return replace_window(
        gateway,
        account_id=account_id,
        window_start=window_start,
        window_end=window_end,
        events=events,
    )
```

### C2. `src/cli.py`

(1) Docstring — find:

```python
Chunk 9 surface: `inboxmind connect`, `inboxmind sync`, and `inboxmind brief`.
```

Replace with:

```python
Chunk 10 surface: `inboxmind connect`, `inboxmind sync` (mail plus a
read-only calendar window), and `inboxmind brief` (agenda-first triage).
```

(2) Find:

```python
from src.ingestion.graph_auth import MicrosoftGraphOAuthSettings
```

Replace with:

```python
from src.ingestion.graph_auth import MicrosoftGraphOAuthSettings
from src.ingestion.graph_calendar import GraphCalendarError
```

(3) Find:

```python
from src.sync_service import SyncReport, run_sync
```

Replace with:

```python
from src.sync_service import DEFAULT_CALENDAR_DAYS, SyncReport, run_sync
```

(4) Find:

```python
    if args.command == "sync":
        return _run_sync(client_factory, gateway_factory, transport_factory)
```

Replace with:

```python
    if args.command == "sync":
        return _run_sync(
            client_factory, gateway_factory, transport_factory, calendar_days=args.calendar_days
        )
```

(5) Find:

```python
    subparsers.add_parser(
        "sync",
        help="Pull mailbox changes through delta sync into encrypted Supabase storage.",
    )
```

Replace with:

```python
    sync_parser = subparsers.add_parser(
        "sync",
        help="Pull mailbox changes and a calendar window into encrypted Supabase storage.",
    )
    sync_parser.add_argument(
        "--calendar-days",
        type=int,
        default=DEFAULT_CALENDAR_DAYS,
        help=f"Fetch events for today +/- N days (default {DEFAULT_CALENDAR_DAYS}, minimum 1).",
    )
```

(6) Find:

```python
def _run_sync(
    client_factory: ClientFactory,
    gateway_factory: GatewayFactory,
    transport_factory: TransportFactory,
) -> int:
    app_settings = _load_settings(AppSettings, env_prefix="")
```

Replace with:

```python
def _run_sync(
    client_factory: ClientFactory,
    gateway_factory: GatewayFactory,
    transport_factory: TransportFactory,
    *,
    calendar_days: int,
) -> int:
    if calendar_days < 1:
        print("Configuration error: --calendar-days must be at least 1.")
        return EXIT_CONFIG_ERROR
    app_settings = _load_settings(AppSettings, env_prefix="")
```

(7) Find:

```python
            consent_records=consent_records,
        )
```

Replace with:

```python
            consent_records=consent_records,
            calendar_days=calendar_days,
        )
```

(8) Find:

```python
    except GraphTransportError as exc:
        print(f"Sync failed after retries: {exc}")
        return EXIT_FAILURE
```

Replace with:

```python
    except GraphTransportError as exc:
        print(f"Sync failed after retries: {exc}")
        return EXIT_FAILURE
    except GraphCalendarError as exc:
        print(f"Calendar sync failed: {exc}")
        print("Mail progress was already checkpointed; re-run `inboxmind sync` once fixed.")
        return EXIT_FAILURE
```

(9) Find:

```python
    print(f"  Consents uploaded: {report.consents_uploaded}. Delta checkpoint saved.")
```

Replace with:

```python
    print(
        f"  Calendar: {report.calendar_events_stored} events stored "
        f"for today +/- {report.calendar_days} day(s)."
    )
    print(f"  Consents uploaded: {report.consents_uploaded}. Delta checkpoint saved.")
```

### C3. `tests/integration/test_sync_end_to_end.py`

(1) Replace the whole `from tests.fakes import (...)` block with:

```python
from tests.fakes import (
    FakeTableGateway,
    ScriptedGraphTransport,
    empty_calendar_script,
    graph_event,
    graph_message,
    make_consent,
    make_token,
    removed_message,
    todays_calendar_url,
    todays_event_time,
)
```

(2) After the line `DELTA_LINK_TWO = "https://graph.microsoft.com/v1.0/delta?token=two"` add:

```python
CALENDAR_URL = todays_calendar_url()
```

(3) Every `ScriptedGraphTransport({...})` in the four existing tests gains
`**empty_calendar_script(),` as the last entry of its responses dict — the
scripted transport raises on any unscripted URL, and every `run_sync` now
requests the calendar. There are five transports to touch (test 3 has two).
Example for test 1 — find:

```python
            DELTA_LINK_ONE: {
                "value": [graph_message("m-0003", body="Body three")],
                "@odata.deltaLink": DELTA_LINK_TWO,
            },
        }
    )
```

Replace with:

```python
            DELTA_LINK_ONE: {
                "value": [graph_message("m-0003", body="Body three")],
                "@odata.deltaLink": DELTA_LINK_TWO,
            },
            **empty_calendar_script(),
        }
    )
```

Apply the same `**empty_calendar_script(),` addition to the transports in
`test_duplicate_ids...`, both transports in `test_stale_delta_state...`, and
`test_deleted_upstream...` (for dicts whose last entry ends `}` without a
trailing comma, add the comma first).

(4) Find:

```python
    assert transport.requested_urls == [INITIAL_URL, DELTA_LINK_ONE]
```

Replace with:

```python
    assert first.calendar_events_stored == 0
    assert first.calendar_days == 1
    assert transport.requested_urls == [
        INITIAL_URL,
        CALENDAR_URL,
        DELTA_LINK_ONE,
        CALENDAR_URL,
    ]
```

(5) Find:

```python
    # Exactly two requests: the stale error must not burn transport retries.
    assert stale_transport.requested_urls == [DELTA_LINK_ONE, INITIAL_URL]
```

Replace with:

```python
    # The stale error must not burn transport retries; calendar follows mail.
    assert stale_transport.requested_urls == [DELTA_LINK_ONE, INITIAL_URL, CALENDAR_URL]
```

(6) Append a new test at end of file:

```python
def test_calendar_events_stored_and_replaced_across_syncs() -> None:
    gateway = FakeTableGateway()
    encryptor = make_encryptor()
    first_transport = ScriptedGraphTransport(
        {
            INITIAL_URL: {
                "value": [graph_message("m-4001")],
                "@odata.deltaLink": DELTA_LINK_ONE,
            },
            CALENDAR_URL: {
                "value": [
                    graph_event("evt-0001", subject="Standup"),
                    graph_event(
                        "evt-0002",
                        subject="Client review",
                        start=todays_event_time(18),
                        end=todays_event_time(19),
                    ),
                ]
            },
        }
    )

    first = run_sync(
        token=make_token(),
        transport=first_transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[],
    )

    assert first.calendar_events_stored == 2
    rows = gateway.tables["calendar_events"]
    assert {row["provider_event_id"] for row in rows} == {"evt-0001", "evt-0002"}
    account_id = gateway.tables["accounts"][0]["id"]
    assert all(row["account_id"] == account_id for row in rows)

    second_transport = ScriptedGraphTransport(
        {
            DELTA_LINK_ONE: {"value": [], "@odata.deltaLink": DELTA_LINK_TWO},
            CALENDAR_URL: {"value": [graph_event("evt-0001", subject="Standup (moved)")]},
        }
    )

    second = run_sync(
        token=make_token(),
        transport=second_transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[],
    )

    assert second.calendar_events_stored == 1
    rows = gateway.tables["calendar_events"]
    assert len(rows) == 1
    assert rows[0]["subject"] == "Standup (moved)"
```

### C4. `tests/unit/test_cli_sync.py`

(1) Find:

```python
    "scope": "User.Read Mail.Read",
```

Replace with:

```python
    "scope": "User.Read Mail.Read Calendars.Read",
```

(2) Find:

```python
from tests.fakes import FakeTableGateway, ScriptedGraphTransport, graph_message, make_consent
```

Replace with:

```python
from tests.fakes import (
    FakeTableGateway,
    ScriptedGraphTransport,
    empty_calendar_script,
    graph_message,
    make_consent,
)
```

(3) Find:

```python
            build_initial_delta_url(): {
                "value": [graph_message("m-0001", body="Body one")],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?token=one",
            }
        }
    )
```

Replace with:

```python
            build_initial_delta_url(): {
                "value": [graph_message("m-0001", body="Body one")],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?token=one",
            },
            **empty_calendar_script(),
        }
    )
```

(4) Find:

```python
    assert "1 stored encrypted" in output
```

Replace with:

```python
    assert "1 stored encrypted" in output
    assert "Calendar: 0 events stored for today +/- 1 day(s)." in output
```

(5) Append a new test at end of file:

```python
def test_sync_rejects_calendar_days_below_one(
    sync_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["sync", "--calendar-days", "0"], client_factory=silent_client_factory)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "--calendar-days must be at least 1" in output
```

### Checkpoint C

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest -q
```

Expected: all pass, 0 failed. (`tests/unit/test_cli_brief.py` must still pass
untouched — if it fails here, stop and report.)

---

## Phase D — Brief: agenda + meeting-aware boost + test updates

### D1. `src/models/brief_models.py`

(1) Find:

```python
from src.models.email_models import UrgencyBand
```

Replace with:

```python
from src.models.calendar_models import CalendarEvent
from src.models.email_models import UrgencyBand
```

(2) Find:

```python
    message_count: int = Field(ge=1)
    latest_at: datetime
```

Replace with:

```python
    message_count: int = Field(ge=1)
    latest_at: datetime
    boost_reason: str | None = None
```

(3) Find:

```python
    generated_at: datetime
    threads: list[BriefThreadSummary] = Field(default_factory=list)
```

Replace with:

```python
    generated_at: datetime
    events: list[CalendarEvent] = Field(default_factory=list)
    threads: list[BriefThreadSummary] = Field(default_factory=list)
```

### D2. `src/brief_service.py`

(1) Find:

```python
from datetime import UTC, datetime, timedelta
```

Replace with:

```python
from datetime import UTC, datetime, time, timedelta
```

(2) Find:

```python
from src.memory.account_store import ACCOUNTS_TABLE, link_account_persona, persona_profile_id
from src.memory.email_store import EMAILS_TABLE
```

Replace with:

```python
from src.memory.account_store import ACCOUNTS_TABLE, link_account_persona, persona_profile_id
from src.memory.calendar_store import load_events
from src.memory.email_store import EMAILS_TABLE
```

(3) Find:

```python
from src.memory.supabase_client import TableGateway
```

Replace with:

```python
from src.memory.supabase_client import SupabaseStoreError, TableGateway
```

(4) Find:

```python
from src.models.brief_models import URGENCY_ORDER, BriefThreadSummary, FilingProposal, MorningBrief
```

Replace with:

```python
from src.models.brief_models import URGENCY_ORDER, BriefThreadSummary, FilingProposal, MorningBrief
from src.models.calendar_models import CalendarEvent
```

(5) Find:

```python
    EmailAddress,
    Provider,
)
```

Replace with:

```python
    EmailAddress,
    Provider,
    UrgencyBand,
)
```

(6) Find:

```python
DEFAULT_LOOKBACK_HOURS = 24
```

Replace with:

```python
AGENDA_LOOKBACK_DAYS = 7  # how far back a still-running multi-day event can start
DEFAULT_LOOKBACK_HOURS = 24
```

(7) Find:

```python
    rules = SupabaseRuleStore(gateway).list_rules(account_id)
    proposals = _build_proposals(supervisor, account_id, rows, classified, rules)
    threads = _build_threads(rows, classified, persona.profile_id, account_zone)
    return MorningBrief(
```

Replace with:

```python
    rules = SupabaseRuleStore(gateway).list_rules(account_id)
    proposals = _build_proposals(supervisor, account_id, rows, classified, rules)
    events, attendee_emails = _agenda(
        gateway, account_id, moment, account_zone, str(account.get("primary_email"))
    )
    threads = _build_threads(rows, classified, persona.profile_id, account_zone, attendee_emails)
    return MorningBrief(
```

(8) Find:

```python
        generated_at=moment.astimezone(account_zone),
        threads=threads,
```

Replace with:

```python
        generated_at=moment.astimezone(account_zone),
        events=events,
        threads=threads,
```

(9) Find:

```python
def _build_threads(
    rows: list[dict[str, Any]],
    classified: dict[str, Classification],
    profile_id: str,
    account_zone: ZoneInfo,
) -> list[BriefThreadSummary]:
```

Replace with:

```python
def _build_threads(
    rows: list[dict[str, Any]],
    classified: dict[str, Classification],
    profile_id: str,
    account_zone: ZoneInfo,
    attendee_emails: set[str],
) -> list[BriefThreadSummary]:
```

(10) Find:

```python
        urgency = min(
            (classified[str(member["id"])].urgency for member in members),
            key=lambda band: URGENCY_ORDER[band],
        )
```

Replace with:

```python
        base_urgency = min(
            (classified[str(member["id"])].urgency for member in members),
            key=lambda band: URGENCY_ORDER[band],
        )
        urgency, boost_reason = _boosted_urgency(base_urgency, members, attendee_emails)
```

(11) Find:

```python
                urgency=urgency,
                message_count=len(members),
                latest_at=_timestamp(latest).astimezone(account_zone),
```

Replace with:

```python
                urgency=urgency,
                message_count=len(members),
                latest_at=_timestamp(latest).astimezone(account_zone),
                boost_reason=boost_reason,
```

(12) Insert this block immediately **after** the end of `_build_threads`
(after its `return threads` line and before `def _timestamp`):

```python
_BAND_BY_RANK = {rank: band for band, rank in URGENCY_ORDER.items()}


def _boosted_urgency(
    base: UrgencyBand,
    members: list[dict[str, Any]],
    attendee_emails: set[str],
) -> tuple[UrgencyBand, str | None]:
    """Meeting-aware boost is a display-time overlay; stored classifications
    are never rewritten, so re-runs stay deterministic."""
    if URGENCY_ORDER[base] == 0:
        return base, None
    for member in members:
        sender = str(member.get("sender_email")).lower()
        if sender in attendee_emails:
            boosted = _BAND_BY_RANK[URGENCY_ORDER[base] - 1]
            return boosted, f"boosted from {base.value}: meeting today with {sender}"
    return base, None


def _agenda(
    gateway: TableGateway,
    account_id: str,
    moment: datetime,
    zone: ZoneInfo,
    owner_email: str,
) -> tuple[list[CalendarEvent], set[str]]:
    """Today's agenda (account-zone display copies) and the boost attendee set.

    An event is on today's agenda when its [start, end) range overlaps today's
    local day. Overlap - not starts-today - so all-day invites created in
    other time zones and cross-midnight meetings still surface; the trade-off
    is a foreign-timezone all-day event may also appear on a neighboring day.
    """
    day_start = datetime.combine(moment.astimezone(zone).date(), time.min, tzinfo=zone)
    day_end = day_start + timedelta(days=1)
    day_start_utc = day_start.astimezone(UTC)
    day_end_utc = day_end.astimezone(UTC)
    try:
        stored = load_events(
            gateway,
            account_id=account_id,
            start=day_start_utc - timedelta(days=AGENDA_LOOKBACK_DAYS),
            end=day_end_utc,
        )
    except SupabaseStoreError as exc:
        msg = f"Stored calendar events are unreadable: {exc}"
        raise BriefDataError(msg) from exc
    todays = [event for event in stored if event.start < day_end_utc and event.end > day_start_utc]
    owner = owner_email.lower()
    attendee_emails = {email for event in todays for email in event.participant_emails()} - {owner}
    display = [_display_event(event, zone, owner) for event in todays]
    return display, attendee_emails


def _display_event(event: CalendarEvent, zone: ZoneInfo, owner_email: str) -> CalendarEvent:
    return event.model_copy(
        update={
            "start": event.start.astimezone(zone),
            "end": event.end.astimezone(zone),
            "attendees": [a for a in event.attendees if a.email != owner_email],
        }
    )
```

### D3. `src/brief/renderer.py`

(1) Find:

```python
from src.models.brief_models import URGENCY_ORDER, BriefThreadSummary, FilingProposal, MorningBrief
from src.models.email_models import UrgencyBand
```

Replace with:

```python
from src.models.brief_models import URGENCY_ORDER, BriefThreadSummary, FilingProposal, MorningBrief
from src.models.calendar_models import CalendarEvent
from src.models.email_models import UrgencyBand
```

(2) Find:

```python
_BAND_TITLES: dict[UrgencyBand, str] = {
```

Replace with:

```python
_ATTENDEE_DISPLAY_CAP = 4

_BAND_TITLES: dict[UrgencyBand, str] = {
```

(3) Find:

```python
    lines.append(_triage_line(brief))
```

Replace with:

```python
    lines.extend(["", "## Agenda", ""])
    if brief.events:
        lines.extend(_event_line(event) for event in brief.events)
    else:
        lines.append("No meetings today.")
    lines.append("")
    lines.append(_triage_line(brief))
```

(4) Find:

```python
    return (
        f"- **{thread.subject}** - {senders} "
        f"({thread.message_count} message{plural}, latest {latest}) [{thread.profile_id}]"
    )
```

Replace with:

```python
    line = (
        f"- **{thread.subject}** - {senders} "
        f"({thread.message_count} message{plural}, latest {latest}) [{thread.profile_id}]"
    )
    if thread.boost_reason:
        line += f" - {thread.boost_reason}"
    return line
```

(5) Insert after the end of `_thread_line` (before `def _proposal_line`):

```python
def _event_line(event: CalendarEvent) -> str:
    if event.is_all_day:
        window = "All day:"
    else:
        window = f"{event.start.strftime('%H:%M')}-{event.end.strftime('%H:%M')}"
    subject = event.subject or "(no subject)"
    return f"- {window} **{subject}**{_event_details(event)}"


def _event_details(event: CalendarEvent) -> str:
    details = ""
    if event.attendees:
        shown = [attendee.name or attendee.email for attendee in event.attendees]
        overflow = len(shown) - _ATTENDEE_DISPLAY_CAP
        if overflow > 0:
            shown = shown[:_ATTENDEE_DISPLAY_CAP]
        people = ", ".join(shown)
        if overflow > 0:
            people += f" +{overflow} more"
        details += f" - with {people}"
    if event.location:
        details += f" ({event.location})"
    if event.online_meeting_url:
        details += f" - join: {event.online_meeting_url}"
    return details
```

### D4. `tests/unit/test_brief_renderer.py`

(1) Find:

```python
from src.models.brief_models import BriefThreadSummary, FilingProposal, MorningBrief
```

Replace with:

```python
from src.models.brief_models import BriefThreadSummary, FilingProposal, MorningBrief
from src.models.calendar_models import CalendarEvent, EventAttendee
```

(2) Find:

```python
def make_brief(
    threads: list[BriefThreadSummary] | None = None,
    proposals: list[FilingProposal] | None = None,
) -> MorningBrief:
```

Replace with:

```python
def make_brief(
    threads: list[BriefThreadSummary] | None = None,
    proposals: list[FilingProposal] | None = None,
    events: list[CalendarEvent] | None = None,
) -> MorningBrief:
```

(3) Find:

```python
        threads=threads or [],
```

Replace with:

```python
        events=events or [],
        threads=threads or [],
```

(4) Append at end of file:

```python
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
        "with Casey Lee, person1@example.com, person2@example.com, "
        "person3@example.com +2 more"
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
```

### D5. `tests/integration/test_brief_end_to_end.py`

(1) Replace the imports block — find:

```python
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
```

Replace with:

```python
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
```

(2) Find:

```python
                "@odata.deltaLink": DELTA_LINK,
            }
        }
    )
```

Replace with:

```python
                "@odata.deltaLink": DELTA_LINK,
            },
            **empty_calendar_script(),
        }
    )
```

(3) Append at end of file. Ordering matters: the event is seeded **after**
`synced_gateway()` because sync's own (empty) replace-window would prune
seeded rows whenever the real clock is near 2026-07-04. The seeded instants
are fixed to the FIXED_NOW day so the test is deterministic on any run date.

```python
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
```

### Checkpoint D

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest -q
```

Expected: all pass, 0 failed. Roughly 150 tests total — record the exact
count for the changelog.

---

## Phase E — Full validation + smoke

```bash
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
uv run python scripts/secret_scan.py
uv run inboxmind --help
uv run inboxmind sync --help
```

All green; `sync --help` must show `--calendar-days`. Record the pytest
total (`N passed`) and the delta vs the 121 baseline for the changelog.

---

## Phase F — Docs, version, commit, PR, CI, wrap-up

### F1. `docs/manual.md`

(1) Find:

```markdown
3. API permissions: delegated `User.Read` and `Mail.Read` only. Do not add
   `Mail.Send` or `Mail.ReadWrite`.
```

Replace with:

```markdown
3. API permissions: delegated `User.Read`, `Mail.Read`, and `Calendars.Read`
   only. Do not add `Mail.Send`, `Mail.ReadWrite`, or `Calendars.ReadWrite`.
```

(2) At the end of the "## Sync (Chunk 8)" section (after the paragraph ending
"...until `inboxmind brief --profile` links a real YAML persona."), append:

```markdown
From chunk 10 each sync also fetches a read-only calendar window
(`--calendar-days N` widens it from the default today +/- 1 day) into the
`calendar_events` table after the mail checkpoint is saved, replacing the
whole window each run so cancelled or moved meetings never linger. Event
bodies are never stored.

Upgrading from 0.4.0: add the delegated `Calendars.Read` permission to the
app registration, run the `calendar_events` block from `supabase/schema.sql`
(table, index, row level security, policy) in the Supabase SQL editor once,
then re-run `uv run inboxmind connect` so the cached token gains the new
scope. Until then, `inboxmind sync` reports a calendar error naming exactly
that fix.
```

(3) At the end of the "## Brief (Chunk 9)" section, append:

```markdown
From chunk 10 the brief opens with today's agenda (times in the account's
timezone, all-day events flagged, join links included) before email triage,
and mail from anyone on today's attendee list is boosted one urgency band
for display (capped at critical) with the reason shown on the thread line —
stored classifications are never rewritten.
```

### F2. `README.md`

(1) Find:

```markdown
first Morning Brief (`brief-YYYY-MM-DD.md`). See `docs/manual.md` for
app-registration, Supabase, and persona setup.
```

Replace with:

```markdown
first Morning Brief (`brief-YYYY-MM-DD.md`) — and, from chunk 10, `sync`
also pulls a read-only calendar window (`Calendars.Read`) so the brief
opens with today's agenda and boosts mail from today's attendees one
urgency band (display-only, reason recorded). See `docs/manual.md` for
app-registration, Supabase, and persona setup.
```

(2) Find:

```markdown
Next focus:
- chunk 10: read-only calendar (`Calendars.Read`) agenda and meeting-aware triage
- chunks 11-12: review/learning loop, then local-only drafts
```

Replace with:

```markdown
Next focus:
- chunk 11: `inboxmind review` — accept/modify/reject proposals feeding the learning loop
- chunk 12: local-only persona drafts
```

### F3. `docs/production-instructions.md`

(1) Find (the in-progress status block written during the 2026-07-04 docs
alignment):

```markdown
Status: in progress (2026-07-04) on branch `codex/chunk-10-calendar-read`.
The calendar models, Graph calendarView client, storage layer, gateway
growth, and schema table are on disk and audited. To finish, execute
`docs/2026-07-04 - Chunk 10 completion plan.md` — phases A-F with exact
edits, per-phase checkpoints, and the PR/CI protocol. That plan supersedes
every other chunk-10 task list; the done criteria below remain the
acceptance contract. Expected baseline: exactly 4 failing tests in
`tests/unit/test_graph_token_cache.py`, repaired in phase A.
```

Replace with:

```markdown
Status: delivered 2026-07-04 (PR #NN). Built from
`docs/2026-07-04 - Chunk 10 completion plan.md`. Real-run verification
remains a manual step for Adam: add the `Calendars.Read` API permission to
the app registration, apply the `calendar_events` block of
`supabase/schema.sql`, re-run `inboxmind connect` once, then
`inboxmind sync` and `inboxmind brief`; steps are in `docs/manual.md`.
```

(Replace `NN` with the real PR number after F6.)

(2) In "## Current Recommendation", change the say-this prompt
`Finish chunk 10: execute docs/2026-07-04 - Chunk 10 completion plan.md.` to
`Carry on with chunk 11.` and replace the closing paragraph ("Chunk 10 is
half-built and audited ... recommends chunk 11.") with:

```markdown
That closes the feedback loop: `inboxmind review` records
accept/modify/reject decisions as feedback records, LearningAgent earns rule
promotions after three consecutive accepts (and stays the only
`filing_rules` writer), and the proposal acceptance rate that drives the
write-scope gate appears in the brief footer.
```

### F4. `docs/CHANGELOG.md`

Insert directly under the `# Changelog` heading (fill in the two counts from
Phase E):

```markdown
## 0.5.0 - 2026-07-04

- Chunk 10 (Calendar Read): `inboxmind sync` now also fetches a read-only
  Microsoft Graph `calendarView` window (`Calendars.Read`; today +/- 1 day,
  `--calendar-days N` to widen) after the mail checkpoint is saved, and the
  Morning Brief opens with today's agenda before email triage.
- Provider-neutral `CalendarEvent`/`EventAttendee` models: timezone-aware
  start/end, organizer, deduped lowercased attendees, location,
  online-meeting URL, and a 500-character body excerpt matching the email
  discipline — event bodies are never persisted at all.
- New `calendar_events` table (index, RLS, service-role policy) with
  replace-window semantics: each sync deletes the fetched window plus any
  rows for refetched event ids, then inserts fresh, so cancelled and moved
  meetings never linger; duplicate provider ids collapse last-wins.
- Meeting-aware triage: mail from anyone on today's attendee list is boosted
  one urgency band for display (capped at critical) with the reason recorded
  on the thread line; stored classifications are never rewritten. Today is
  the account-timezone day, and events qualify by overlap so cross-midnight
  and foreign-timezone all-day meetings still surface.
- `Calendars.Read` joined the enforced scope set (`Calendars.ReadWrite`
  stays rejected by the `.ReadWrite` fragment guard, now covered by tests);
  `TableGateway` gained `lt` filtering and `delete_rows`.
- NN new tests (NNN total). Zero new dependencies.
```

### F5. Version bump

In `pyproject.toml` change `version = "0.4.0"` to `version = "0.5.0"`, then:

```bash
uv sync --all-groups
```

(`uv.lock` updates; commit it.)

### F6. Commit, push, PR

```bash
git add -A
git status --short
# Review: only files named in this plan may appear, plus the 2026-07-04
# docs-alignment changes already in the working tree (this plan document
# and docs/production-instructions.md). They belong in this chunk commit.
git commit -m "[calendar] feat: add read-only calendar agenda with meeting-aware triage"
git push -u origin codex/chunk-10-calendar-read
gh pr create --title "[calendar] feat: read-only calendar agenda with meeting-aware triage (chunk 10)" --body "$(cat <<'EOF'
## Chunk 10: Calendar Read — Agenda In The Brief

- `Calendars.Read` joins the enforced scope set; `Calendars.ReadWrite` rejected by tests.
- Provider-neutral `CalendarEvent` (tz-aware start/end, organizer, attendees, location, join URL); event bodies obey the 500-char excerpt discipline and are never persisted.
- `inboxmind sync` fetches today +/- N days (`--calendar-days`, default 1) after the mail checkpoint saves; replace-window storage prunes cancelled/moved events.
- Meeting-aware urgency: mail from today's attendees boosted one band (capped at critical), reason recorded on the thread line; stored classifications untouched.
- Brief shows the agenda before email triage.
- Manual step for Adam (docs/manual.md): add `Calendars.Read` to the app registration, apply the `calendar_events` schema block, re-run `inboxmind connect` once.

Validation: ruff format/check, mypy, pytest (NNN passed), secret scan — all green. Zero new dependencies.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Then patch the `PR #NN` placeholder in `docs/production-instructions.md` with
the real number, `git add`/`git commit --amend --no-edit`… **no** — amend
would re-run hooks needlessly and rewrite a pushed commit. Instead: commit the
placeholder fix as a tiny follow-up on the same branch:

```bash
git add docs/production-instructions.md
git commit -m "[docs] docs: record chunk 10 PR number"
git push
```

### F7. CI wait

`gh pr checks <N> --json` does **not** work on this machine. Poll with plain
exit codes (0 = passed, 8 = pending, 1 = failure):

```bash
gh pr checks <N>; echo "exit: $?"
```

Re-check every ~30-60 s until exit 0 (or report the failing check's log).

### F8. Wrap-up report to Adam (shape)

PDCA summary: what shipped (map to the five done criteria), validation
results with test counts, the manual steps (app-registration permission,
schema block, one `inboxmind connect`), any deviations from this plan. End
by offering the merge of the new PR and recommending: **"Carry on with
chunk 11."** Do not merge without Adam's approval; his "carry on with
chunk 11" reply is the merge authorization per the established flow.

---

## Traceability: done criteria → implementation → proof

| Done criterion (verbatim) | Implementation | Test |
| --- | --- | --- |
| `Calendars.Read` joins the allowed scope set; `Calendars.ReadWrite` is rejected by tests | `GRAPH_REQUIRED_SCOPES` in `graph_auth.py` (done); `.ReadWrite` fragment guard (pre-existing) | `test_graph_auth.py::test_required_scopes_include_read_only_calendar`, `::test_graph_oauth_settings_reject_write_capable_calendar_scopes` (A2) |
| `CalendarEvent` carries tz-aware start/end, organizer, attendees, location, online-meeting URL; body obeys excerpt discipline | `calendar_models.py` (done); mapper in `graph_calendar.py` (done); store never persists bodies (done) | `test_calendar_models.py` (B4), `test_graph_calendar.py` mapping tests (B5), `test_calendar_store.py::test_round_trip...` (B6) |
| `inboxmind sync` fetches today +/- configurable days | `_sync_calendar` + `calendar_days` param (C1); `--calendar-days` flag (C2) | sync e2e URL/replace tests (C3), `test_cli_sync.py` happy path + `--calendar-days 0` (C4) |
| Meeting-aware urgency boost, capped at critical, reason recorded | `_boosted_urgency` + `_agenda` in `brief_service.py` (D2); `boost_reason` field (D1) | `test_meeting_attendee_boosts_display_urgency_only` (D5) |
| Brief shows the agenda before email triage | renderer agenda section (D3); `MorningBrief.events` (D1) | `test_agenda_renders_between_window_and_triage` (D4), agenda-before-Triage assert in D5 |

## Accepted risks and intentional non-changes

- **Midnight-rollover URL race**: a test computing `todays_calendar_url()` in
  a different UTC day than `run_sync`'s clock would mismatch. Probability is
  negligible; the failure is a loud `ScriptedGraphTransport` assertion. If it
  ever flakes in CI, script both days' URLs in the fixture.
- **Foreign-timezone all-day events** may appear on a neighboring day (overlap
  rule); missing a meeting is the failure mode we optimized against.
- **Multi-day events starting more than 7 days ago** (`AGENDA_LOOKBACK_DAYS`)
  drop off the agenda; acceptable for MVP.
- **Calendar failure after mail success exits 1** even though mail progress
  is safe (checkpoint saved first); the CLI says so explicitly. Deliberate.
- **Not touched, deliberately**: `make_consent` fixture scopes (historical
  record), `tests/unit/test_cli_brief.py` (must stay green unmodified),
  `docs/architecture.md` (already documents the Calendar Read Boundary),
  `docs/roadmap.md`, `.env.example` (the window is a CLI flag, not an env
  var), token-cache/MSAL code, and the entire mail pipeline.
