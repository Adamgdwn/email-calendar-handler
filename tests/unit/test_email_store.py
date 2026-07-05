from __future__ import annotations

from datetime import UTC, datetime

from src.memory.email_store import (
    EncryptedEmailRecord,
    SupabaseEmailStore,
    prepare_encrypted_email_record,
)
from src.models.email_models import AccountContext, EmailAddress, Provider, RawEmail
from src.utils.encryption import FieldEncryptor
from tests.fakes import FakeTableGateway


def make_account_context() -> AccountContext:
    return AccountContext(
        account_id="acct-prime",
        profile_id="prime_boilers",
        provider=Provider.MICROSOFT_GRAPH,
        display_name="Prime Boilers",
        primary_email="ops@primeboilers.example",
        org_type="commercial",
    )


def make_raw_email(
    message_id: str = "msg-1",
    *,
    thread_id: str = "thread-1",
    body_text: str = "Synthetic body that should be encrypted.",
    timestamp: datetime | None = None,
) -> RawEmail:
    return RawEmail(
        message_id=message_id,
        thread_id=thread_id,
        sender=EmailAddress(address="Sender@Example.com"),
        recipients=[EmailAddress(address="Recipient@Example.com")],
        subject="Synthetic storage test",
        body_text=body_text,
        timestamp=timestamp or datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
        labels=["Client"],
    )


def make_record(
    encryptor: FieldEncryptor,
    message_id: str = "msg-1",
    *,
    thread_id: str = "thread-1",
    body_text: str = "Synthetic body that should be encrypted.",
    timestamp: datetime | None = None,
) -> EncryptedEmailRecord:
    return prepare_encrypted_email_record(
        make_account_context(),
        make_raw_email(message_id, thread_id=thread_id, body_text=body_text, timestamp=timestamp),
        encryptor,
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


def test_store_batch_creates_thread_rows_and_ciphertext_only_email_rows() -> None:
    encryptor = FieldEncryptor(FieldEncryptor.generate_key())
    gateway = FakeTableGateway()
    store = SupabaseEmailStore(gateway)
    records = [
        make_record(encryptor),
        make_record(encryptor, "msg-2", thread_id="thread-2", body_text="A different body."),
    ]

    result = store.store_batch("acct-prime", records)

    assert result.inserted == 2
    assert result.skipped_duplicates == 0
    threads = gateway.tables["threads"]
    assert {row["provider_thread_id"] for row in threads} == {"thread-1", "thread-2"}
    emails = gateway.tables["emails"]
    assert len(emails) == 2
    thread_ids_by_provider = {row["provider_thread_id"]: row["id"] for row in threads}
    for row in emails:
        assert row["account_id"] == "acct-prime"
        assert "provider_thread_id" not in row
        assert "body_text" not in row
        assert row["thread_id"] in thread_ids_by_provider.values()


def test_store_batch_skips_duplicate_ids_and_body_hashes_in_batch() -> None:
    encryptor = FieldEncryptor(FieldEncryptor.generate_key())
    store = SupabaseEmailStore(FakeTableGateway())
    records = [
        make_record(encryptor),
        make_record(encryptor),
        make_record(encryptor, "msg-2", thread_id="thread-2"),
    ]

    result = store.store_batch("acct-prime", records)

    assert result.inserted == 1
    assert result.skipped_duplicates == 2


def test_store_batch_skips_records_already_in_storage() -> None:
    encryptor = FieldEncryptor(FieldEncryptor.generate_key())
    gateway = FakeTableGateway()
    store = SupabaseEmailStore(gateway)

    first = store.store_batch("acct-prime", [make_record(encryptor)])
    second = store.store_batch("acct-prime", [make_record(encryptor)])

    assert first.inserted == 1
    assert second.inserted == 0
    assert second.skipped_duplicates == 1
    assert len(gateway.tables["emails"]) == 1
    assert len(gateway.tables["threads"]) == 1


def test_thread_last_activity_moves_forward_only() -> None:
    encryptor = FieldEncryptor(FieldEncryptor.generate_key())
    gateway = FakeTableGateway()
    store = SupabaseEmailStore(gateway)
    early = datetime(2026, 5, 15, 11, 0, tzinfo=UTC)
    late = datetime(2026, 5, 15, 13, 0, tzinfo=UTC)

    store.store_batch("acct-prime", [make_record(encryptor, "msg-1", body_text="one")])
    store.store_batch(
        "acct-prime", [make_record(encryptor, "msg-2", body_text="two", timestamp=late)]
    )
    store.store_batch(
        "acct-prime", [make_record(encryptor, "msg-3", body_text="three", timestamp=early)]
    )

    threads = gateway.tables["threads"]
    assert len(threads) == 1
    assert threads[0]["last_activity"] == late.isoformat()
