from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from src.models.email_models import AccountContext, EmailThread, Provider, RawEmail


class ProviderCheckpointKind(StrEnum):
    GRAPH_DELTA_LINK = "graph_delta_link"
    GMAIL_HISTORY_ID = "gmail_history_id"


class ProviderSyncCheckpoint(BaseModel):
    account_id: str
    provider: Provider
    mail_folder_id: str = "inbox"
    graph_delta_link: str | None = None
    gmail_history_id: str | None = None

    @model_validator(mode="after")
    def provider_checkpoint_must_match_provider(self) -> ProviderSyncCheckpoint:
        if self.provider == Provider.MICROSOFT_GRAPH and self.gmail_history_id is not None:
            msg = "Microsoft Graph checkpoints must not use gmail_history_id"
            raise ValueError(msg)
        if self.provider == Provider.GMAIL and self.graph_delta_link is not None:
            msg = "Gmail checkpoints must not use graph_delta_link"
            raise ValueError(msg)
        return self

    @property
    def kind(self) -> ProviderCheckpointKind | None:
        if self.graph_delta_link is not None:
            return ProviderCheckpointKind.GRAPH_DELTA_LINK
        if self.gmail_history_id is not None:
            return ProviderCheckpointKind.GMAIL_HISTORY_ID
        return None


class ProviderSyncResult(BaseModel):
    account_context: AccountContext
    raw_emails: list[RawEmail] = Field(default_factory=list)
    threads: list[EmailThread] = Field(default_factory=list)
    checkpoint: ProviderSyncCheckpoint


class ProviderEmailAdapter(Protocol):
    def sync(
        self, account_context: AccountContext, checkpoint: ProviderSyncCheckpoint
    ) -> ProviderSyncResult:
        """Return provider data normalized to InboxMind contracts."""
