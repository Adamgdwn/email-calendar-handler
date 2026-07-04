from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from src.models.email_models import EmailAddress, EmailThread, RawEmail

SECONDS_PER_DAY = 86_400


def assemble_email_threads(emails: Iterable[RawEmail]) -> list[EmailThread]:
    grouped: dict[str, list[RawEmail]] = defaultdict(list)
    for email in emails:
        grouped[email.thread_id].append(email)

    threads = [_build_thread(thread_id, messages) for thread_id, messages in grouped.items()]
    return sorted(
        threads, key=lambda thread: (thread.last_activity, thread.thread_id), reverse=True
    )


def _build_thread(thread_id: str, messages: list[RawEmail]) -> EmailThread:
    sorted_messages = sorted(messages, key=lambda email: (email.timestamp, email.message_id))
    first_activity = sorted_messages[0].timestamp
    last_activity = sorted_messages[-1].timestamp
    duration_days = (last_activity - first_activity).total_seconds() / SECONDS_PER_DAY

    return EmailThread(
        thread_id=thread_id,
        messages=sorted_messages,
        participant_set=_participant_set(sorted_messages),
        duration_days=duration_days,
        last_activity=last_activity,
    )


def _participant_set(messages: Iterable[RawEmail]) -> set[str]:
    participants: set[str] = set()
    for message in messages:
        participants.add(_normalize_address(message.sender))
        participants.update(_normalize_address(recipient) for recipient in message.recipients)
    return participants


def _normalize_address(email_address: EmailAddress) -> str:
    return str(email_address.address).lower()
