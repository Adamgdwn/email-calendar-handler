"""Microsoft Graph folder tree and message metadata fetcher for inbox audit."""

from __future__ import annotations

from typing import Any, Protocol

from src.models.audit_models import FolderNode, MessageMetadataRow

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_FOLDER_TREE_URL = f"{GRAPH_BASE_URL}/me/mailFolders?$expand=childFolders&$top=100"
_MESSAGE_SELECT = "sender,subject,receivedDateTime"
_MESSAGE_TOP = 999


class FolderFetchTransport(Protocol):
    def get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]: ...


class AuditFetchError(RuntimeError):
    """Raised when Graph returns unexpected data during an audit fetch."""


class FolderFetcher:
    """Fetches folder tree and message metadata from Microsoft Graph.

    Never decrypts bodies; reads only sender, subject, and receivedDateTime.
    """

    def __init__(self, transport: FolderFetchTransport, access_token: str) -> None:
        self._transport = transport
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def fetch_folder_tree(self) -> list[FolderNode]:
        """Return top-level folders with one level of childFolders expanded."""
        payload = self._transport.get_json(_FOLDER_TREE_URL, self._headers)
        raw_folders = payload.get("value", [])
        if not isinstance(raw_folders, list):
            msg = "Unexpected response shape from mailFolders endpoint"
            raise AuditFetchError(msg)
        return [self._parse_folder_node(f) for f in raw_folders]

    def fetch_message_metadata(
        self,
        folder_id: str,
        folder_path: list[str],
        cutoff_iso: str,
    ) -> list[MessageMetadataRow]:
        """Fetch all message metadata from one folder since cutoff; follows @odata.nextLink."""
        url: str = (
            f"{GRAPH_BASE_URL}/me/mailFolders/{folder_id}/messages"
            f"?$select={_MESSAGE_SELECT}"
            f"&$top={_MESSAGE_TOP}"
            f"&$filter=receivedDateTime ge {cutoff_iso}"
        )
        rows: list[MessageMetadataRow] = []
        while url:
            payload = self._transport.get_json(url, self._headers)
            messages = payload.get("value", [])
            if not isinstance(messages, list):
                break
            for msg in messages:
                row = self._parse_metadata_row(msg, folder_path)
                if row is not None:
                    rows.append(row)
            url = str(payload.get("@odata.nextLink") or "")
        return rows

    def _parse_folder_node(self, raw: dict[str, Any]) -> FolderNode:
        child_folders = [
            self._parse_folder_node(child) for child in (raw.get("childFolders") or [])
        ]
        return FolderNode(
            folder_id=str(raw.get("id", "")),
            display_name=str(raw.get("displayName", "")),
            parent_id=raw.get("parentFolderId"),
            message_count=int(raw.get("totalItemCount", 0)),
            child_folders=child_folders,
        )

    def _parse_metadata_row(
        self, raw: dict[str, Any], folder_path: list[str]
    ) -> MessageMetadataRow | None:
        sender_info = raw.get("sender") or {}
        email_addr = str((sender_info.get("emailAddress") or {}).get("address", ""))
        domain = email_addr.split("@")[-1] if "@" in email_addr else (email_addr or "unknown")
        subject = str(raw.get("subject") or "")[:60]
        received = str(raw.get("receivedDateTime") or "")
        received_month = received[:7] if len(received) >= 7 else ""
        return MessageMetadataRow(
            folder_path=folder_path,
            sender_domain=domain,
            subject_prefix=subject,
            received_month=received_month,
        )
