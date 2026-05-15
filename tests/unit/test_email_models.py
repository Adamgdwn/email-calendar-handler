from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.email_models import EmailAddress, EmailThread, RawEmail


def test_raw_email_requires_timezone_aware_timestamp() -> None:
    email = RawEmail(
        message_id="msg-1",
        thread_id="thread-1",
        sender=EmailAddress(address="sender@example.com"),
        recipients=[EmailAddress(address="recipient@example.com")],
        subject="Status",
        body_text="Synthetic fixture body.",
        timestamp=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
        labels=["INBOX"],
    )

    assert email.timestamp.tzinfo is UTC


def test_raw_email_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        RawEmail(
            message_id="msg-1",
            thread_id="thread-1",
            sender=EmailAddress(address="sender@example.com"),
            recipients=[EmailAddress(address="recipient@example.com")],
            subject="Status",
            body_text="Synthetic fixture body.",
            timestamp=datetime(2026, 5, 15, 12, 0),
        )


def test_email_thread_contract() -> None:
    email = RawEmail(
        message_id="msg-1",
        thread_id="thread-1",
        sender=EmailAddress(address="sender@example.com"),
        recipients=[EmailAddress(address="recipient@example.com")],
        subject="Status",
        body_text="Synthetic fixture body.",
        timestamp=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )

    thread = EmailThread(
        thread_id="thread-1",
        messages=[email],
        participant_set={"sender@example.com", "recipient@example.com"},
        duration_days=0,
        last_activity=email.timestamp,
    )

    assert thread.messages[0].message_id == "msg-1"
