from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from hashlib import sha256
from html.parser import HTMLParser

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from src.models.email_models import AccountContext, EmailAddress, RawEmail


class GraphEmailAddress(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    address: EmailStr


class GraphRecipient(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    email_address: GraphEmailAddress = Field(alias="emailAddress")


class GraphItemBody(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    content_type: str = Field(default="text", alias="contentType")
    content: str = ""


class GraphMessagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    conversation_id: str = Field(alias="conversationId")
    sender: GraphRecipient | None = None
    from_recipient: GraphRecipient | None = Field(default=None, alias="from")
    to_recipients: list[GraphRecipient] = Field(default_factory=list, alias="toRecipients")
    cc_recipients: list[GraphRecipient] = Field(default_factory=list, alias="ccRecipients")
    bcc_recipients: list[GraphRecipient] = Field(default_factory=list, alias="bccRecipients")
    subject: str = ""
    body: GraphItemBody | None = None
    body_preview: str = Field(default="", alias="bodyPreview")
    received_date_time: datetime = Field(alias="receivedDateTime")
    categories: list[str] = Field(default_factory=list)

    @field_validator("received_date_time")
    @classmethod
    def received_date_time_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "receivedDateTime must be timezone-aware"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def require_sender_or_from(self) -> GraphMessagePayload:
        if self.sender is None and self.from_recipient is None:
            msg = "Graph message must include sender or from"
            raise ValueError(msg)
        return self


class EmailDedupeKeys(BaseModel):
    account_id: str
    provider_message_id: str
    account_body_hash: str


class DuplicateEmailKeys(BaseModel):
    provider_message_ids: set[str] = Field(default_factory=set)
    account_body_hashes: set[str] = Field(default_factory=set)

    @property
    def has_duplicates(self) -> bool:
        return bool(self.provider_message_ids or self.account_body_hashes)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self._parts.append(stripped)

    def text(self) -> str:
        return " ".join(self._parts)


def map_graph_message_to_raw_email(message: GraphMessagePayload) -> RawEmail:
    sender = _map_sender(message)
    return RawEmail(
        message_id=message.id,
        thread_id=message.conversation_id,
        sender=sender,
        recipients=_map_recipients(message),
        subject=message.subject or "",
        body_text=_body_text(message),
        timestamp=message.received_date_time,
        labels=_labels(message),
    )


def dedupe_keys_for_email(account_context: AccountContext, email: RawEmail) -> EmailDedupeKeys:
    return EmailDedupeKeys(
        account_id=account_context.account_id,
        provider_message_id=email.message_id,
        account_body_hash=account_scoped_body_hash(account_context.account_id, email.body_text),
    )


def account_scoped_body_hash(account_id: str, body_text: str) -> str:
    canonical_body = body_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return sha256(f"{account_id}\0{canonical_body}".encode()).hexdigest()


def detect_duplicate_email_keys(keys: Iterable[EmailDedupeKeys]) -> DuplicateEmailKeys:
    seen_message_ids: set[tuple[str, str]] = set()
    seen_body_hashes: set[tuple[str, str]] = set()
    duplicate_message_ids: set[str] = set()
    duplicate_body_hashes: set[str] = set()

    for item in keys:
        message_identity = (item.account_id, item.provider_message_id)
        body_identity = (item.account_id, item.account_body_hash)

        if message_identity in seen_message_ids:
            duplicate_message_ids.add(item.provider_message_id)
        seen_message_ids.add(message_identity)

        if body_identity in seen_body_hashes:
            duplicate_body_hashes.add(item.account_body_hash)
        seen_body_hashes.add(body_identity)

    return DuplicateEmailKeys(
        provider_message_ids=duplicate_message_ids,
        account_body_hashes=duplicate_body_hashes,
    )


def _map_sender(message: GraphMessagePayload) -> EmailAddress:
    sender = message.sender or message.from_recipient
    if sender is None:
        msg = "Graph message must include sender or from"
        raise ValueError(msg)
    return _map_email_address(sender.email_address)


def _map_recipients(message: GraphMessagePayload) -> list[EmailAddress]:
    recipients = [
        *message.to_recipients,
        *message.cc_recipients,
        *message.bcc_recipients,
    ]
    mapped: list[EmailAddress] = []
    seen: set[str] = set()
    for recipient in recipients:
        email_address = _map_email_address(recipient.email_address)
        address_key = str(email_address.address).lower()
        if address_key not in seen:
            mapped.append(email_address)
            seen.add(address_key)
    return mapped


def _map_email_address(value: GraphEmailAddress) -> EmailAddress:
    return EmailAddress(name=value.name, address=str(value.address).lower())


def _body_text(message: GraphMessagePayload) -> str:
    if message.body is None:
        return message.body_preview

    if message.body.content_type.lower() == "html":
        extractor = _HTMLTextExtractor()
        extractor.feed(message.body.content)
        extracted = extractor.text()
        return extracted or message.body_preview

    return message.body.content or message.body_preview


def _labels(message: GraphMessagePayload) -> list[str]:
    return list(dict.fromkeys(label for label in message.categories if label))
