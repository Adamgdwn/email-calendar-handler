from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.ingestion.graph_mapper import account_scoped_body_hash
from src.memory.supabase_client import SupabaseStoreError, TableGateway
from src.models.email_models import AccountContext, RawEmail
from src.utils.encryption import FieldEncryptor

THREADS_TABLE = "threads"
EMAILS_TABLE = "emails"
QUERY_CHUNK_SIZE = 100
INSERT_CHUNK_SIZE = 500


class EncryptedEmailRecord(BaseModel):
    account_id: str
    provider_message_id: str
    provider_thread_id: str
    sender_email: str
    recipient_emails: list[str]
    subject: str
    body_ciphertext: str
    body_hash: str
    message_timestamp: datetime
    labels: list[str] = Field(default_factory=list)


class EmailBatchResult(BaseModel):
    inserted: int = 0
    skipped_duplicates: int = 0


def prepare_encrypted_email_record(
    account_context: AccountContext,
    email: RawEmail,
    encryptor: FieldEncryptor,
) -> EncryptedEmailRecord:
    return EncryptedEmailRecord(
        account_id=account_context.account_id,
        provider_message_id=email.message_id,
        provider_thread_id=email.thread_id,
        sender_email=str(email.sender.address).lower(),
        recipient_emails=[str(recipient.address).lower() for recipient in email.recipients],
        subject=email.subject,
        body_ciphertext=encryptor.encrypt_text(email.body_text),
        body_hash=account_scoped_body_hash(account_context.account_id, email.body_text),
        message_timestamp=email.timestamp,
        labels=email.labels,
    )


class SupabaseEmailStore:
    """Dedupe-aware batch writer: thread rows first, then ciphertext-only email rows."""

    def __init__(self, gateway: TableGateway) -> None:
        self._gateway = gateway

    def store_batch(self, account_id: str, records: list[EncryptedEmailRecord]) -> EmailBatchResult:
        fresh = self._drop_duplicates(account_id, records)
        if not fresh:
            return EmailBatchResult(inserted=0, skipped_duplicates=len(records))
        thread_ids = self._ensure_threads(account_id, fresh)
        payloads: list[dict[str, Any]] = []
        for record in fresh:
            payload = record.model_dump(mode="json")
            payload["thread_id"] = thread_ids[record.provider_thread_id]
            del payload["provider_thread_id"]
            payloads.append(payload)
        for chunk in _chunked(payloads, INSERT_CHUNK_SIZE):
            self._gateway.insert_rows(EMAILS_TABLE, chunk)
        return EmailBatchResult(inserted=len(fresh), skipped_duplicates=len(records) - len(fresh))

    def _drop_duplicates(
        self, account_id: str, records: list[EncryptedEmailRecord]
    ) -> list[EncryptedEmailRecord]:
        seen_message_ids = self._existing_column_values(
            account_id, "provider_message_id", [record.provider_message_id for record in records]
        )
        seen_body_hashes = self._existing_column_values(
            account_id, "body_hash", [record.body_hash for record in records]
        )
        fresh: list[EncryptedEmailRecord] = []
        for record in records:
            if record.provider_message_id in seen_message_ids:
                continue
            if record.body_hash in seen_body_hashes:
                continue
            seen_message_ids.add(record.provider_message_id)
            seen_body_hashes.add(record.body_hash)
            fresh.append(record)
        return fresh

    def _existing_column_values(self, account_id: str, column: str, values: list[str]) -> set[str]:
        found: set[str] = set()
        for chunk in _chunked(sorted(set(values)), QUERY_CHUNK_SIZE):
            rows = self._gateway.select_rows(
                EMAILS_TABLE, column, eq={"account_id": account_id}, in_filter=(column, chunk)
            )
            found.update(str(row[column]) for row in rows if column in row)
        return found

    def _ensure_threads(
        self, account_id: str, records: list[EncryptedEmailRecord]
    ) -> dict[str, str]:
        latest: dict[str, datetime] = {}
        for record in records:
            current = latest.get(record.provider_thread_id)
            if current is None or record.message_timestamp > current:
                latest[record.provider_thread_id] = record.message_timestamp
        provider_thread_ids = sorted(latest)
        thread_ids: dict[str, str] = {}
        stored_activity: dict[str, datetime] = {}
        for chunk in _chunked(provider_thread_ids, QUERY_CHUNK_SIZE):
            rows = self._gateway.select_rows(
                THREADS_TABLE,
                "id,provider_thread_id,last_activity",
                eq={"account_id": account_id},
                in_filter=("provider_thread_id", chunk),
            )
            for row in rows:
                provider_thread_id = str(row.get("provider_thread_id"))
                thread_ids[provider_thread_id] = str(row.get("id"))
                raw_activity = row.get("last_activity")
                if isinstance(raw_activity, str):
                    stored_activity[provider_thread_id] = datetime.fromisoformat(raw_activity)
        missing = [pid for pid in provider_thread_ids if pid not in thread_ids]
        for chunk in _chunked(missing, INSERT_CHUNK_SIZE):
            inserted = self._gateway.insert_rows(
                THREADS_TABLE,
                [
                    {
                        "account_id": account_id,
                        "provider_thread_id": provider_thread_id,
                        "last_activity": _isoformat_utc(latest[provider_thread_id]),
                    }
                    for provider_thread_id in chunk
                ],
            )
            for row in inserted:
                thread_ids[str(row.get("provider_thread_id"))] = str(row.get("id"))
        for provider_thread_id, previous_activity in stored_activity.items():
            if latest[provider_thread_id] > previous_activity:
                self._gateway.update_rows(
                    THREADS_TABLE,
                    {"last_activity": _isoformat_utc(latest[provider_thread_id])},
                    eq={"account_id": account_id, "provider_thread_id": provider_thread_id},
                )
        unresolved = [pid for pid in provider_thread_ids if pid not in thread_ids]
        if unresolved:
            msg = f"Supabase did not return ids for thread rows: {unresolved[:3]}"
            raise SupabaseStoreError(msg)
        return thread_ids


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _chunked[T](items: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
