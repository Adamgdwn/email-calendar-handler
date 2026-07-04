from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from src.memory.email_store import (
    EncryptedEmailRecord,
    SupabaseEmailStore,
    prepare_encrypted_email_record,
)
from src.models.email_models import AccountContext, EmailAddress, Provider, RawEmail
from src.utils.encryption import FieldEncryptor


class FakeExecuteResponse(BaseModel):
    ok: bool = True


class FakeInsertRequest:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def execute(self) -> FakeExecuteResponse:
        return FakeExecuteResponse()


class FakeTableClient:
    def __init__(self) -> None:
        self.inserted_payloads: list[dict[str, object]] = []

    def insert(self, payload: dict[str, object]) -> FakeInsertRequest:
        self.inserted_payloads.append(payload)
        return FakeInsertRequest(payload)


def make_account_context() -> AccountContext:
    return AccountContext(
        account_id="acct-prime",
        profile_id="prime_boilers",
        provider=Provider.MICROSOFT_GRAPH,
        display_name="Prime Boilers",
        primary_email="ops@primeboilers.example",
        org_type="commercial",
    )


def make_raw_email() -> RawEmail:
    return RawEmail(
        message_id="msg-1",
        thread_id="thread-1",
        sender=EmailAddress(address="Sender@Example.com"),
        recipients=[EmailAddress(address="Recipient@Example.com")],
        subject="Synthetic storage test",
        body_text="Synthetic body that should be encrypted.",
        timestamp=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
        labels=["Client"],
    )


def test_prepare_encrypted_email_record_encrypts_body() -> None:
    encryptor = FieldEncryptor(FieldEncryptor.generate_key())
    email = make_raw_email()

    record = prepare_encrypted_email_record(make_account_context(), email, encryptor)

    assert record.body_ciphertext != email.body_text
    assert encryptor.decrypt_text(record.body_ciphertext) == email.body_text
    assert record.account_id == "acct-prime"
    assert record.provider_message_id == "msg-1"
    assert record.provider_thread_id == "thread-1"
    assert record.sender_email == "sender@example.com"
    assert record.recipient_emails == ["recipient@example.com"]
    assert record.labels == ["Client"]


def test_encrypted_email_record_has_no_plaintext_body_field() -> None:
    record_fields = set(EncryptedEmailRecord.model_fields)

    assert "body_text" not in record_fields
    assert "body_ciphertext" in record_fields


def test_supabase_email_store_accepts_typed_encrypted_record() -> None:
    encryptor = FieldEncryptor(FieldEncryptor.generate_key())
    record = prepare_encrypted_email_record(make_account_context(), make_raw_email(), encryptor)
    table_client = FakeTableClient()
    store = SupabaseEmailStore(table_client)

    result = store.insert_email(record)

    assert result.inserted is True
    assert result.provider_message_id == "msg-1"
    assert table_client.inserted_payloads[0]["provider_message_id"] == "msg-1"
    assert "body_ciphertext" in table_client.inserted_payloads[0]
    assert "body_text" not in table_client.inserted_payloads[0]
