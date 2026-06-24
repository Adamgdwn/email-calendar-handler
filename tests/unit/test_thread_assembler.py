from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.ingestion.thread_assembler import assemble_email_threads
from src.models.email_models import EmailAddress, RawEmail


def make_email(
    *,
    message_id: str,
    thread_id: str,
    sender: str,
    recipients: list[str],
    timestamp: datetime,
) -> RawEmail:
    return RawEmail(
        message_id=message_id,
        thread_id=thread_id,
        sender=EmailAddress(address=sender),
        recipients=[EmailAddress(address=recipient) for recipient in recipients],
        subject="Synthetic thread test",
        body_text="Synthetic body.",
        timestamp=timestamp,
    )


def test_assembles_single_message_thread() -> None:
    timestamp = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
    email = make_email(
        message_id="msg-1",
        thread_id="thread-1",
        sender="Sender@Example.com",
        recipients=["Recipient@Example.com"],
        timestamp=timestamp,
    )

    threads = assemble_email_threads([email])

    assert len(threads) == 1
    assert threads[0].thread_id == "thread-1"
    assert threads[0].messages == [email]
    assert threads[0].participant_set == {"sender@example.com", "recipient@example.com"}
    assert threads[0].duration_days == 0
    assert threads[0].last_activity == timestamp


def test_assembles_multi_message_thread_chronologically() -> None:
    start = datetime(2026, 5, 15, 9, 0, tzinfo=UTC)
    newest = start + timedelta(days=2, hours=6)
    middle = start + timedelta(hours=4)
    emails = [
        make_email(
            message_id="msg-3",
            thread_id="thread-1",
            sender="service@primeboilers.example",
            recipients=["alex@example.com"],
            timestamp=newest,
        ),
        make_email(
            message_id="msg-1",
            thread_id="thread-1",
            sender="alex@example.com",
            recipients=["ops@primeboilers.example"],
            timestamp=start,
        ),
        make_email(
            message_id="msg-2",
            thread_id="thread-1",
            sender="ops@primeboilers.example",
            recipients=["alex@example.com", "service@primeboilers.example"],
            timestamp=middle,
        ),
    ]

    thread = assemble_email_threads(emails)[0]

    assert [email.message_id for email in thread.messages] == ["msg-1", "msg-2", "msg-3"]
    assert thread.participant_set == {
        "alex@example.com",
        "ops@primeboilers.example",
        "service@primeboilers.example",
    }
    assert thread.duration_days == 2.25
    assert thread.last_activity == newest


def test_assembles_multiple_threads_by_latest_activity() -> None:
    older = datetime(2026, 5, 15, 9, 0, tzinfo=UTC)
    newer = datetime(2026, 5, 16, 9, 0, tzinfo=UTC)
    emails = [
        make_email(
            message_id="msg-1",
            thread_id="older-thread",
            sender="a@example.com",
            recipients=["b@example.com"],
            timestamp=older,
        ),
        make_email(
            message_id="msg-2",
            thread_id="newer-thread",
            sender="c@example.com",
            recipients=["d@example.com"],
            timestamp=newer,
        ),
    ]

    threads = assemble_email_threads(emails)

    assert [thread.thread_id for thread in threads] == ["newer-thread", "older-thread"]


def test_empty_email_list_returns_no_threads() -> None:
    assert assemble_email_threads([]) == []
