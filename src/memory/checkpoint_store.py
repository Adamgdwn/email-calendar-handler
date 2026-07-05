"""Read/write provider sync checkpoints in `account_sync_checkpoints`."""

from __future__ import annotations

from datetime import UTC, datetime

from src.ingestion.provider_contracts import ProviderSyncCheckpoint
from src.memory.supabase_client import TableGateway
from src.models.email_models import Provider

CHECKPOINTS_TABLE = "account_sync_checkpoints"


class CheckpointStore:
    def __init__(self, gateway: TableGateway) -> None:
        self._gateway = gateway

    def load(
        self, *, account_id: str, provider: Provider, mail_folder_id: str
    ) -> ProviderSyncCheckpoint:
        rows = self._gateway.select_rows(
            CHECKPOINTS_TABLE,
            "graph_delta_link,gmail_history_id",
            eq={
                "account_id": account_id,
                "provider": provider.value,
                "mail_folder_id": mail_folder_id,
            },
        )
        graph_delta_link = rows[0].get("graph_delta_link") if rows else None
        gmail_history_id = rows[0].get("gmail_history_id") if rows else None
        return ProviderSyncCheckpoint(
            account_id=account_id,
            provider=provider,
            mail_folder_id=mail_folder_id,
            graph_delta_link=graph_delta_link if isinstance(graph_delta_link, str) else None,
            gmail_history_id=gmail_history_id if isinstance(gmail_history_id, str) else None,
        )

    def save(self, checkpoint: ProviderSyncCheckpoint) -> None:
        self._gateway.upsert_rows(
            CHECKPOINTS_TABLE,
            [
                {
                    "account_id": checkpoint.account_id,
                    "provider": checkpoint.provider.value,
                    "mail_folder_id": checkpoint.mail_folder_id,
                    "graph_delta_link": checkpoint.graph_delta_link,
                    "gmail_history_id": checkpoint.gmail_history_id,
                    "updated_at": datetime.now(tz=UTC).isoformat(),
                }
            ],
            on_conflict="account_id,provider,mail_folder_id",
        )

    def clear(self, *, account_id: str, provider: Provider, mail_folder_id: str) -> None:
        """Explicit resync path: drop stored delta state so the next sync starts fresh."""
        self._gateway.update_rows(
            CHECKPOINTS_TABLE,
            {
                "graph_delta_link": None,
                "gmail_history_id": None,
                "updated_at": datetime.now(tz=UTC).isoformat(),
            },
            eq={
                "account_id": account_id,
                "provider": provider.value,
                "mail_folder_id": mail_folder_id,
            },
        )
