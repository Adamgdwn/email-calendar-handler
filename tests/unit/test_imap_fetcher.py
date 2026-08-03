"""Tests for IMAP header fetcher — imaplib is mocked; no network calls."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.imap_auth import ImapCredentials
from src.ingestion.imap_fetcher import fetch_imap_raw_emails


@pytest.fixture
def creds() -> ImapCredentials:
    return ImapCredentials(
        host="imap.shaw.ca",
        port=993,
        username="user@shaw.ca",
        password="synthetic-test-pw",  # noqa: S106
    )


def _raw_header(
    subject: str = "Test subject",
    from_addr: str = "Sender <sender@example.com>",
    date: str = "Mon, 01 Jan 2024 12:00:00 +0000",
    message_id: str = "<abc123@example.com>",
) -> bytes:
    return (
        f"From: {from_addr}\r\n"
        f"Subject: {subject}\r\n"
        f"Date: {date}\r\n"
        f"Message-ID: {message_id}\r\n"
        f"\r\n"
    ).encode()


def _make_imap_mock(
    search_ids: list[bytes] | None = None,
    headers_per_id: list[bytes] | None = None,
) -> MagicMock:
    if search_ids is None:
        search_ids = [b"1"]
    if headers_per_id is None:
        headers_per_id = [_raw_header()]

    imap = MagicMock()
    imap.__enter__ = lambda s: s
    imap.__exit__ = MagicMock(return_value=False)
    imap.login.return_value = ("OK", [b"Logged in"])
    imap.select.return_value = ("OK", [b"1"])
    imap.search.return_value = ("OK", [b" ".join(search_ids)])

    _ids = search_ids
    _hdrs = headers_per_id

    def fake_fetch(num: bytes, cmd: str) -> tuple[str, list[object]]:
        idx = _ids.index(num)
        raw = _hdrs[idx] if idx < len(_hdrs) else _hdrs[-1]
        return ("OK", [(b"1 (BODY[...])", raw), b")"])

    imap.fetch.side_effect = fake_fetch
    return imap


# ── basic fetch ───────────────────────────────────────────────────────────────


def test_fetch_returns_raw_email(creds: ImapCredentials) -> None:
    mock_imap = _make_imap_mock()
    since = datetime(2024, 1, 1, tzinfo=UTC)
    with patch("src.ingestion.imap_fetcher.imaplib.IMAP4_SSL", return_value=mock_imap):
        results = fetch_imap_raw_emails(creds, since=since)

    assert len(results) == 1
    email = results[0]
    assert email.subject == "Test subject"
    assert str(email.sender.address) == "sender@example.com"
    assert email.labels == ["INBOX"]


def test_fetch_maps_subject_and_sender(creds: ImapCredentials) -> None:
    mock_imap = _make_imap_mock(
        headers_per_id=[_raw_header(subject="Hello world", from_addr="Alice <alice@example.com>")]
    )
    since = datetime(2024, 1, 1, tzinfo=UTC)
    with patch("src.ingestion.imap_fetcher.imaplib.IMAP4_SSL", return_value=mock_imap):
        results = fetch_imap_raw_emails(creds, since=since)

    assert results[0].subject == "Hello world"
    assert str(results[0].sender.address) == "alice@example.com"
    assert results[0].sender.name == "Alice"


def test_fetch_uses_message_id_as_provider_id(creds: ImapCredentials) -> None:
    mock_imap = _make_imap_mock(
        headers_per_id=[_raw_header(message_id="<unique-id-xyz@mail.example.com>")]
    )
    since = datetime(2024, 1, 1, tzinfo=UTC)
    with patch("src.ingestion.imap_fetcher.imaplib.IMAP4_SSL", return_value=mock_imap):
        results = fetch_imap_raw_emails(creds, since=since)

    assert results[0].message_id == "<unique-id-xyz@mail.example.com>"


def test_fetch_timestamp_is_timezone_aware(creds: ImapCredentials) -> None:
    mock_imap = _make_imap_mock()
    since = datetime(2024, 1, 1, tzinfo=UTC)
    with patch("src.ingestion.imap_fetcher.imaplib.IMAP4_SSL", return_value=mock_imap):
        results = fetch_imap_raw_emails(creds, since=since)

    assert results[0].timestamp.tzinfo is not None


# ── empty mailbox ─────────────────────────────────────────────────────────────


def test_empty_search_returns_empty_list(creds: ImapCredentials) -> None:
    imap = MagicMock()
    imap.__enter__ = lambda s: s
    imap.__exit__ = MagicMock(return_value=False)
    imap.login.return_value = ("OK", [b"Logged in"])
    imap.select.return_value = ("OK", [b"0"])
    imap.search.return_value = ("OK", [b""])

    since = datetime(2024, 1, 1, tzinfo=UTC)
    with patch("src.ingestion.imap_fetcher.imaplib.IMAP4_SSL", return_value=imap):
        results = fetch_imap_raw_emails(creds, since=since)

    assert results == []


# ── multiple messages ─────────────────────────────────────────────────────────


def test_multiple_messages_returned(creds: ImapCredentials) -> None:
    mock_imap = _make_imap_mock(
        search_ids=[b"1", b"2"],
        headers_per_id=[
            _raw_header(subject="First", message_id="<first@example.com>"),
            _raw_header(subject="Second", message_id="<second@example.com>"),
        ],
    )
    since = datetime(2024, 1, 1, tzinfo=UTC)
    with patch("src.ingestion.imap_fetcher.imaplib.IMAP4_SSL", return_value=mock_imap):
        results = fetch_imap_raw_emails(creds, since=since)

    assert len(results) == 2
    subjects = {r.subject for r in results}
    assert subjects == {"First", "Second"}


# ── body_text uniqueness ──────────────────────────────────────────────────────


def test_body_text_is_unique_per_message(creds: ImapCredentials) -> None:
    mock_imap = _make_imap_mock(
        search_ids=[b"1", b"2"],
        headers_per_id=[
            _raw_header(subject="Same", message_id="<a@example.com>"),
            _raw_header(subject="Same", message_id="<b@example.com>"),
        ],
    )
    since = datetime(2024, 1, 1, tzinfo=UTC)
    with patch("src.ingestion.imap_fetcher.imaplib.IMAP4_SSL", return_value=mock_imap):
        results = fetch_imap_raw_emails(creds, since=since)

    assert results[0].body_text != results[1].body_text
