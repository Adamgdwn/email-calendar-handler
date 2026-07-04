from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from src.ingestion.graph_mapper import GraphMessagePayload, map_graph_message_to_raw_email
from src.models.email_models import RawEmail

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
DEFAULT_MAIL_FOLDER_ID = "inbox"
GRAPH_DELTA_SELECT_FIELDS = (
    "id",
    "conversationId",
    "sender",
    "from",
    "toRecipients",
    "ccRecipients",
    "bccRecipients",
    "subject",
    "body",
    "bodyPreview",
    "receivedDateTime",
    "categories",
)


class GraphDeltaStateExpiredError(RuntimeError):
    """Raised when Microsoft Graph says a delta token can no longer be used."""


class GraphTransport(Protocol):
    def get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        """Return a decoded Microsoft Graph JSON response."""


class GraphDeltaCheckpoint(BaseModel):
    account_id: str
    mail_folder_id: str = DEFAULT_MAIL_FOLDER_ID
    delta_link: str | None = None


class GraphDeltaPage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    value: list[dict[str, Any]] = Field(default_factory=list)
    next_link: HttpUrl | None = Field(default=None, alias="@odata.nextLink")
    delta_link: HttpUrl | None = Field(default=None, alias="@odata.deltaLink")

    @model_validator(mode="after")
    def require_exactly_one_state_link(self) -> GraphDeltaPage:
        if self.next_link is None and self.delta_link is None:
            msg = "Graph delta page must include @odata.nextLink or @odata.deltaLink"
            raise ValueError(msg)
        if self.next_link is not None and self.delta_link is not None:
            msg = "Graph delta page cannot include both @odata.nextLink and @odata.deltaLink"
            raise ValueError(msg)
        return self


class GraphDeltaSyncResult(BaseModel):
    mail_folder_id: str
    emails: list[RawEmail]
    deleted_message_ids: list[str] = Field(default_factory=list)
    delta_link: str

    @field_validator("delta_link")
    @classmethod
    def delta_link_must_not_be_empty(cls, value: str) -> str:
        if not value:
            msg = "delta_link must not be empty"
            raise ValueError(msg)
        return value

    def checkpoint(self, account_id: str) -> GraphDeltaCheckpoint:
        return GraphDeltaCheckpoint(
            account_id=account_id,
            mail_folder_id=self.mail_folder_id,
            delta_link=self.delta_link,
        )


def build_initial_delta_url(mail_folder_id: str = DEFAULT_MAIL_FOLDER_ID) -> str:
    select = ",".join(GRAPH_DELTA_SELECT_FIELDS)
    return f"{GRAPH_BASE_URL}/me/mailFolders/{mail_folder_id}/messages/delta?$select={select}"


def run_graph_delta_sync(
    transport: GraphTransport,
    *,
    access_token: str,
    checkpoint: GraphDeltaCheckpoint,
    max_page_size: int = 50,
) -> GraphDeltaSyncResult:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Prefer": f"odata.maxpagesize={max_page_size}",
    }
    next_url = checkpoint.delta_link or build_initial_delta_url(checkpoint.mail_folder_id)
    emails: list[RawEmail] = []
    deleted_message_ids: list[str] = []

    while True:
        payload = transport.get_json(next_url, headers)
        _raise_for_expired_delta_state(payload)
        page = GraphDeltaPage.model_validate(payload)
        for item in page.value:
            if _is_deleted_delta_item(item):
                message_id = item.get("id")
                if isinstance(message_id, str):
                    deleted_message_ids.append(message_id)
                continue
            emails.append(map_graph_message_to_raw_email(GraphMessagePayload.model_validate(item)))

        if page.delta_link is not None:
            return GraphDeltaSyncResult(
                mail_folder_id=checkpoint.mail_folder_id,
                emails=emails,
                deleted_message_ids=deleted_message_ids,
                delta_link=str(page.delta_link),
            )
        if page.next_link is None:
            msg = "Graph delta page did not include a nextLink or deltaLink"
            raise ValueError(msg)
        next_url = str(page.next_link)


def _is_deleted_delta_item(item: dict[str, Any]) -> bool:
    return "@removed" in item


def _raise_for_expired_delta_state(payload: dict[str, Any]) -> None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return

    code = error.get("code")
    if code in {"SyncStateNotFound", "ErrorInvalidSyncStateData", "resyncRequired"}:
        msg = "Microsoft Graph delta state is stale and requires a fresh sync"
        raise GraphDeltaStateExpiredError(msg)
