"""Shared synthetic fakes: an in-memory table gateway, a scripted Graph
transport, and builders for tokens, consents, and Graph message payloads.

Everything here is synthetic; no real mailbox data, ever.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import SecretStr

from src.ingestion.graph_token_cache import GraphTokenResult
from src.models.auth_models import OAuthConsentRecord
from src.models.email_models import Provider

SYNTHETIC_ACCOUNT_ID = "00000000-0000-0000-0000-000000000001.11111111-1111-1111-1111-111111111111"
SYNTHETIC_TENANT_ID = "11111111-1111-1111-1111-111111111111"


class FakeTableGateway:
    """In-memory `TableGateway` mirroring the postgrest behavior the stores use."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self._next_id = 0

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.setdefault(table, [])

    def select_rows(
        self,
        table: str,
        columns: str,
        *,
        eq: dict[str, str],
        in_filter: tuple[str, list[str]] | None = None,
        gte: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        del columns  # the fake returns full rows; callers read only what they selected
        return [dict(row) for row in self.rows(table) if _matches(row, eq, in_filter, gte)]

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stored: list[dict[str, Any]] = []
        for row in rows:
            new_row = dict(row)
            if "id" not in new_row:
                self._next_id += 1
                new_row["id"] = f"row-{self._next_id:04d}"
            self.rows(table).append(new_row)
            stored.append(dict(new_row))
        return stored

    def upsert_rows(
        self, table: str, rows: list[dict[str, Any]], *, on_conflict: str
    ) -> list[dict[str, Any]]:
        conflict_columns = on_conflict.split(",")
        stored: list[dict[str, Any]] = []
        for row in rows:
            existing = next(
                (
                    candidate
                    for candidate in self.rows(table)
                    if all(candidate.get(column) == row.get(column) for column in conflict_columns)
                ),
                None,
            )
            if existing is None:
                stored.extend(self.insert_rows(table, [row]))
            else:
                existing.update(row)
                stored.append(dict(existing))
        return stored

    def update_rows(
        self, table: str, values: dict[str, Any], *, eq: dict[str, str]
    ) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        for row in self.rows(table):
            if _matches(row, eq, None, None):
                row.update(values)
                updated.append(dict(row))
        return updated


def _matches(
    row: dict[str, Any],
    eq: dict[str, str],
    in_filter: tuple[str, list[str]] | None,
    gte: tuple[str, str] | None,
) -> bool:
    if any(row.get(column) != value for column, value in eq.items()):
        return False
    if in_filter is not None:
        column, values = in_filter
        if row.get(column) not in values:
            return False
    if gte is not None:
        column, bound = gte
        return _meets_lower_bound(row.get(column), bound)
    return True


def _meets_lower_bound(value: Any, bound: str) -> bool:
    # Timestamps arrive in mixed ISO renderings ("Z" vs "+00:00"), so compare
    # parsed datetimes and fall back to string ordering for non-timestamp columns.
    try:
        return datetime.fromisoformat(str(value)) >= datetime.fromisoformat(bound)
    except ValueError:
        return str(value) >= bound


class ScriptedGraphTransport:
    """Replays canned Graph JSON payloads by URL and records every request."""

    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.requested_urls: list[str] = []
        self.seen_headers: list[dict[str, str]] = []
        self.closed = False

    def get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        self.requested_urls.append(url)
        self.seen_headers.append(dict(headers))
        if url not in self.responses:
            msg = f"ScriptedGraphTransport has no response for {url}"
            raise AssertionError(msg)
        return self.responses[url]

    def close(self) -> None:
        self.closed = True


def graph_message(
    message_id: str,
    *,
    conversation_id: str = "conv-0001",
    body: str = "Synthetic body",
    received: str = "2026-07-04T15:00:00Z",
    sender: str = "sender@example.com",
    subject: str = "Synthetic subject",
) -> dict[str, Any]:
    return {
        "id": message_id,
        "conversationId": conversation_id,
        "from": {"emailAddress": {"name": "Synthetic Sender", "address": sender}},
        "toRecipients": [{"emailAddress": {"address": "owner@example.com"}}],
        "subject": subject,
        "body": {"contentType": "text", "content": body},
        "bodyPreview": body[:32],
        "receivedDateTime": received,
        "categories": [],
    }


def removed_message(message_id: str) -> dict[str, Any]:
    return {"id": message_id, "@removed": {"reason": "deleted"}}


def make_token(subject: str = "owner@example.com") -> GraphTokenResult:
    return GraphTokenResult(
        access_token=SecretStr("synthetic-access-token"),
        subject=subject,
        account_id=SYNTHETIC_ACCOUNT_ID,
        tenant_id=SYNTHETIC_TENANT_ID,
        account_type="organizational",
        scopes=("User.Read", "Mail.Read"),
        from_cache=True,
    )


def make_consent(
    subject: str = "owner@example.com",
    granted_at: datetime | None = None,
) -> OAuthConsentRecord:
    return OAuthConsentRecord(
        provider=Provider.MICROSOFT_GRAPH,
        account_id=SYNTHETIC_ACCOUNT_ID,
        subject=subject,
        scopes=["User.Read", "Mail.Read"],
        granted_at=granted_at or datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC),
        tenant_id=SYNTHETIC_TENANT_ID,
        account_type="organizational",
    )
