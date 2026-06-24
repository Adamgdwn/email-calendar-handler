from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from src.ingestion.graph_mapper import account_scoped_body_hash
from src.models.email_models import AccountContext, RawEmail
from src.utils.encryption import FieldEncryptor


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


class EmailInsertResult(BaseModel):
    inserted: bool
    provider_message_id: str


class EmailRecordWriter(Protocol):
    def insert_email(self, record: EncryptedEmailRecord) -> EmailInsertResult:
        """Persist an encrypted email record."""


class SupabaseInsertRequest(Protocol):
    def execute(self) -> object:
        """Execute a prepared insert."""


class SupabaseTableClient(Protocol):
    def insert(self, payload: dict[str, object]) -> SupabaseInsertRequest:
        """Prepare an insert payload."""


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
    """Typed adapter boundary for future Supabase email inserts."""

    def __init__(self, table_client: SupabaseTableClient) -> None:
        self._table_client = table_client

    def insert_email(self, record: EncryptedEmailRecord) -> EmailInsertResult:
        payload = record.model_dump(mode="json")
        response = self._table_client.insert(payload).execute()
        _ = response
        return EmailInsertResult(inserted=True, provider_message_id=record.provider_message_id)
