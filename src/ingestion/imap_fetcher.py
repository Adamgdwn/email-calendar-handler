"""Read-only IMAP header fetcher.

Fetches only envelope headers (From, Subject, Date, Message-ID) using
BODY.PEEK so messages are never marked as read.  Body content is never
fetched — policy constraint matches the Graph ingestion path.
"""

from __future__ import annotations

import email.message
import imaplib
import ssl
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from src.ingestion.imap_auth import ImapCredentials
from src.models.email_models import EmailAddress, RawEmail

_FETCH_CMD = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value or ""


def _parse_address(raw: str) -> EmailAddress:
    name, addr = parseaddr(_decode_header(raw))
    clean = addr.lower().strip()
    try:
        return EmailAddress(name=name or None, address=clean)
    except Exception:
        return EmailAddress(name=name or None, address="malformed@placeholder.example")


def _parse_date(raw: str) -> datetime:
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return datetime.now(UTC)


def fetch_imap_raw_emails(
    creds: ImapCredentials,
    *,
    since: datetime,
    folder: str = "INBOX",
) -> list[RawEmail]:
    """Return RawEmail list for messages in *folder* received on or after *since*."""
    ctx = ssl.create_default_context()
    # SECLEVEL=1 allows legacy 1024-bit DH keys used by some ISP servers (e.g. Shaw).
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    results: list[RawEmail] = []
    since_str = since.strftime("%d-%b-%Y")

    with imaplib.IMAP4_SSL(creds.host, creds.port, ssl_context=ctx) as imap:
        imap.login(creds.username, creds.password)
        imap.select(folder, readonly=True)

        _, data = imap.search(None, f'SINCE "{since_str}"')
        if not data or not data[0]:
            return results

        for num in data[0].split():
            _, fetch_data = imap.fetch(num, _FETCH_CMD)
            if not fetch_data or not isinstance(fetch_data[0], tuple):
                continue
            raw_headers = fetch_data[0][1]
            if not isinstance(raw_headers, bytes):
                continue

            msg = email.message_from_bytes(raw_headers)
            subject = _decode_header(msg.get("Subject", ""))
            from_raw = _decode_header(msg.get("From", ""))
            date_raw = msg.get("Date", "")
            message_id = msg.get("Message-ID", "").strip() or f"imap-seq-{num.decode()}"

            results.append(
                RawEmail(
                    message_id=message_id,
                    # IMAP has no server-side thread concept; use message_id as thread_id.
                    thread_id=message_id,
                    sender=_parse_address(from_raw),
                    recipients=[],
                    subject=subject,
                    # Synthetic body ensures unique body_hash per message without
                    # fetching real content.  Classification runs on subject only.
                    body_text=f"imap:uid:{num.decode()}:subject:{subject}",
                    timestamp=_parse_date(date_raw),
                    labels=["INBOX"],
                )
            )

    return results
