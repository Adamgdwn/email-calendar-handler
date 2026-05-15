from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.ingestion.graph_delta import (
    DEFAULT_MAIL_FOLDER_ID,
    GraphDeltaCheckpoint,
    GraphDeltaStateExpiredError,
    build_initial_delta_url,
    run_graph_delta_sync,
)

FIXTURE_PATH = Path("tests/fixtures/outlook_message.json")
SYNTHETIC_AUTH_VALUE = "synthetic" + "-access" + "-value"


class FakeGraphTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self.requested_urls: list[str] = []
        self.requested_headers: list[dict[str, str]] = []

    def get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        self.requested_urls.append(url)
        self.requested_headers.append(headers)
        return self._responses.pop(0)


def fixture_message(message_id: str = "AAMkADSyntheticMessage001") -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(FIXTURE_PATH.read_text())
    payload["id"] = message_id
    return payload


def test_initial_delta_sync_follows_next_link_until_delta_link() -> None:
    next_link = (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$skiptoken=abc"
    )
    delta_link = (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=xyz"
    )
    transport = FakeGraphTransport(
        [
            {
                "value": [fixture_message("message-1")],
                "@odata.nextLink": next_link,
            },
            {
                "value": [fixture_message("message-2")],
                "@odata.deltaLink": delta_link,
            },
        ],
    )

    result = run_graph_delta_sync(
        transport,
        access_token=SYNTHETIC_AUTH_VALUE,
        checkpoint=GraphDeltaCheckpoint(account_id="acct-prime"),
    )

    assert transport.requested_urls == [build_initial_delta_url(DEFAULT_MAIL_FOLDER_ID), next_link]
    assert transport.requested_headers[0]["Authorization"] == f"Bearer {SYNTHETIC_AUTH_VALUE}"
    assert transport.requested_headers[0]["Prefer"] == "odata.maxpagesize=50"
    assert [email.message_id for email in result.emails] == ["message-1", "message-2"]
    assert result.deleted_message_ids == []
    assert result.delta_link == delta_link
    assert result.checkpoint("acct-prime").delta_link == delta_link


def test_subsequent_delta_sync_starts_from_stored_delta_link() -> None:
    stored_delta_link = (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=old"
    )
    new_delta_link = (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=new"
    )
    transport = FakeGraphTransport(
        [
            {
                "value": [fixture_message("message-3")],
                "@odata.deltaLink": new_delta_link,
            },
        ],
    )

    result = run_graph_delta_sync(
        transport,
        access_token=SYNTHETIC_AUTH_VALUE,
        checkpoint=GraphDeltaCheckpoint(
            account_id="acct-prime",
            mail_folder_id="inbox",
            delta_link=stored_delta_link,
        ),
        max_page_size=10,
    )

    assert transport.requested_urls == [stored_delta_link]
    assert transport.requested_headers[0]["Prefer"] == "odata.maxpagesize=10"
    assert [email.message_id for email in result.emails] == ["message-3"]
    assert result.delta_link == new_delta_link


def test_delta_sync_tracks_deleted_message_ids() -> None:
    delta_link = (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=xyz"
    )
    transport = FakeGraphTransport(
        [
            {
                "value": [
                    {"id": "deleted-message", "@removed": {"reason": "deleted"}},
                    fixture_message("message-1"),
                ],
                "@odata.deltaLink": delta_link,
            },
        ],
    )

    result = run_graph_delta_sync(
        transport,
        access_token=SYNTHETIC_AUTH_VALUE,
        checkpoint=GraphDeltaCheckpoint(account_id="acct-prime"),
    )

    assert result.deleted_message_ids == ["deleted-message"]
    assert [email.message_id for email in result.emails] == ["message-1"]


def test_delta_sync_raises_when_graph_delta_state_is_stale() -> None:
    transport = FakeGraphTransport(
        [
            {
                "error": {
                    "code": "SyncStateNotFound",
                    "message": "Synthetic expired delta token.",
                },
            },
        ],
    )

    with pytest.raises(GraphDeltaStateExpiredError):
        run_graph_delta_sync(
            transport,
            access_token=SYNTHETIC_AUTH_VALUE,
            checkpoint=GraphDeltaCheckpoint(
                account_id="acct-prime",
                delta_link="https://graph.microsoft.com/v1.0/me/messages/delta?$deltatoken=old",
            ),
        )


def test_initial_delta_url_is_folder_scoped() -> None:
    assert (
        build_initial_delta_url("archive").split("?", maxsplit=1)[0]
        == "https://graph.microsoft.com/v1.0/me/mailFolders/archive/messages/delta"
    )
