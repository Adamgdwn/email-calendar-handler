from __future__ import annotations

from src.ingestion.graph_auth import GRAPH_REQUIRED_SCOPES
from src.ingestion.graph_delta import (
    DEFAULT_MAIL_FOLDER_ID,
    GraphDeltaCheckpoint,
    GraphDeltaSyncResult,
    GraphTransport,
    run_graph_delta_sync,
)
from src.models.email_models import AccountContext, RawEmail
from src.utils.rate_limiter import retry_provider_call


class MicrosoftGraphClient:
    """Microsoft Graph Outlook client placeholder for Milestone 1.2."""

    required_scopes = GRAPH_REQUIRED_SCOPES

    def __init__(
        self,
        transport: GraphTransport | None = None,
        access_token: str | None = None,
    ) -> None:
        self._transport = transport
        self._access_token = access_token

    def sync_delta(
        self,
        account_context: AccountContext,
        checkpoint: GraphDeltaCheckpoint | None = None,
        mail_folder_id: str = DEFAULT_MAIL_FOLDER_ID,
    ) -> GraphDeltaSyncResult:
        transport = self._transport
        access_token = self._access_token
        if transport is None or access_token is None:
            msg = "MicrosoftGraphClient requires transport and access_token for delta sync"
            raise RuntimeError(msg)
        active_checkpoint = checkpoint or GraphDeltaCheckpoint(
            account_id=account_context.account_id,
            mail_folder_id=mail_folder_id,
        )
        return retry_provider_call(
            lambda: run_graph_delta_sync(
                transport,
                access_token=access_token,
                checkpoint=active_checkpoint,
            ),
        )

    def fetch_delta(
        self,
        account_context: AccountContext,
        delta_link: str | None,
    ) -> list[RawEmail]:
        checkpoint = GraphDeltaCheckpoint(
            account_id=account_context.account_id,
            delta_link=delta_link,
        )
        return self.sync_delta(account_context, checkpoint).emails

    def _fetch_delta_once(
        self,
        account_context: AccountContext,
        delta_link: str | None,
    ) -> list[RawEmail]:
        _ = account_context
        _ = delta_link
        return []
