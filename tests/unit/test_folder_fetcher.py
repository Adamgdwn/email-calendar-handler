"""Unit tests for FolderFetcher using a fake transport."""

from __future__ import annotations

from typing import Any

import pytest

from src.inbox_audit.folder_fetcher import AuditFetchError, FolderFetcher


class FakeTransport:
    """Deterministic transport: returns pre-configured responses by URL prefix."""

    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.calls: list[str] = []
        self._responses = responses

    def get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        self.calls.append(url)
        for prefix in sorted(self._responses, key=len, reverse=True):
            if url.startswith(prefix):
                return self._responses[prefix]
        return {"value": []}


def _folder_payload(
    folder_id: str,
    name: str,
    count: int = 0,
    children: list[dict[str, Any]] | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": folder_id,
        "displayName": name,
        "parentFolderId": parent_id,
        "totalItemCount": count,
        "childFolders": children or [],
    }


def _message_payload(
    address: str, subject: str, received: str = "2025-01-15T10:00:00Z"
) -> dict[str, Any]:
    return {
        "sender": {"emailAddress": {"address": address}},
        "subject": subject,
        "receivedDateTime": received,
    }


# ── Folder tree tests ─────────────────────────────────────────────────────────


def test_fetch_folder_tree_returns_nodes() -> None:
    transport = FakeTransport(
        {"https://graph.microsoft.com": {"value": [_folder_payload("f1", "Inbox", count=10)]}}
    )
    fetcher = FolderFetcher(transport, "tok")
    tree = fetcher.fetch_folder_tree()
    assert len(tree) == 1
    assert tree[0].display_name == "Inbox"
    assert tree[0].message_count == 10
    assert tree[0].folder_id == "f1"


def test_fetch_folder_tree_with_children() -> None:
    child = _folder_payload("f2", "Projects", count=5, parent_id="f1")
    transport = FakeTransport(
        {
            "https://graph.microsoft.com": {
                "value": [_folder_payload("f1", "Inbox", count=20, children=[child])]
            }
        }
    )
    fetcher = FolderFetcher(transport, "tok")
    tree = fetcher.fetch_folder_tree()
    assert len(tree) == 1
    assert len(tree[0].child_folders) == 1
    assert tree[0].child_folders[0].display_name == "Projects"
    assert tree[0].child_folders[0].parent_id == "f1"


def test_fetch_folder_tree_raises_on_bad_shape() -> None:
    transport = FakeTransport({"https://graph.microsoft.com": {"value": "not-a-list"}})
    fetcher = FolderFetcher(transport, "tok")
    with pytest.raises(AuditFetchError):
        fetcher.fetch_folder_tree()


# ── Message metadata tests ────────────────────────────────────────────────────


def test_fetch_message_metadata_extracts_domain() -> None:
    transport = FakeTransport(
        {
            "https://graph.microsoft.com/v1.0/me/mailFolders/f1/messages": {
                "value": [_message_payload("alice@example.com", "Hello")]
            }
        }
    )
    fetcher = FolderFetcher(transport, "tok")
    rows = fetcher.fetch_message_metadata("f1", ["Inbox"], "2025-01-01T00:00:00Z")
    assert len(rows) == 1
    assert rows[0].sender_domain == "example.com"
    assert rows[0].folder_path == ["Inbox"]


def test_fetch_message_metadata_subject_truncated_at_60() -> None:
    long_subject = "X" * 100
    transport = FakeTransport(
        {
            "https://graph.microsoft.com/v1.0/me/mailFolders/f1/messages": {
                "value": [_message_payload("a@b.com", long_subject)]
            }
        }
    )
    fetcher = FolderFetcher(transport, "tok")
    rows = fetcher.fetch_message_metadata("f1", ["Inbox"], "2025-01-01T00:00:00Z")
    assert len(rows[0].subject_prefix) == 60


def test_fetch_message_metadata_received_month() -> None:
    transport = FakeTransport(
        {
            "https://graph.microsoft.com/v1.0/me/mailFolders/f1/messages": {
                "value": [_message_payload("a@b.com", "Hi", received="2025-03-20T08:00:00Z")]
            }
        }
    )
    fetcher = FolderFetcher(transport, "tok")
    rows = fetcher.fetch_message_metadata("f1", ["Inbox"], "2025-01-01T00:00:00Z")
    assert rows[0].received_month == "2025-03"


def test_fetch_message_metadata_paginates() -> None:
    page2_url = "https://graph.microsoft.com/v1.0/me/mailFolders/f1/messages?$skiptoken=abc"
    responses: dict[str, dict[str, Any]] = {
        "https://graph.microsoft.com/v1.0/me/mailFolders/f1/messages": {
            "value": [_message_payload("a@x.com", "First")],
            "@odata.nextLink": page2_url,
        },
        page2_url: {
            "value": [_message_payload("b@y.com", "Second")],
        },
    }
    transport = FakeTransport(responses)
    fetcher = FolderFetcher(transport, "tok")
    rows = fetcher.fetch_message_metadata("f1", ["Inbox"], "2025-01-01T00:00:00Z")
    assert len(rows) == 2
    assert {r.sender_domain for r in rows} == {"x.com", "y.com"}


def test_fetch_message_metadata_no_at_sign_in_address() -> None:
    transport = FakeTransport(
        {
            "https://graph.microsoft.com/v1.0/me/mailFolders/f1/messages": {
                "value": [_message_payload("noemail", "Hi")]
            }
        }
    )
    fetcher = FolderFetcher(transport, "tok")
    rows = fetcher.fetch_message_metadata("f1", ["Inbox"], "2025-01-01T00:00:00Z")
    assert rows[0].sender_domain == "noemail"
