"""Pydantic models for the inbox audit pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class FolderNode(BaseModel):
    folder_id: str
    display_name: str
    parent_id: str | None
    message_count: int
    child_folders: list[FolderNode] = []


class MessageMetadataRow(BaseModel):
    folder_path: list[str]  # e.g. ["Inbox", "Projects"]
    sender_domain: str  # extracted from sender address
    subject_prefix: str  # subject[:60]
    received_month: str  # YYYY-MM


class ClusterGroup(BaseModel):
    label: str
    dominant_folder: str  # existing folder path with most volume
    message_count: int
    sample_subjects: list[str]  # up to 5


class ClusterSummary(BaseModel):
    account_email: str
    months_scanned: int
    total_messages: int
    total_folders: int
    current_folder_tree: list[FolderNode]
    domain_clusters: list[ClusterGroup]
    folder_utilization: dict[str, int]  # folder_path_str → count
    subject_keyword_clusters: list[ClusterGroup]


class ProposedFolder(BaseModel):
    path: list[str]  # e.g. ["Clients", "Acme Corp"]
    rationale: str
    source_folders: list[str]  # existing folders this consolidates
    estimated_volume: int


class FolderAuditProposal(BaseModel):
    account_email: str
    generated_at: datetime
    proposed_tree: list[ProposedFolder]
    folders_to_retire: list[str]
    folders_to_keep: list[str]
    key_changes: list[str]
    implementation_note: str


class AuditReport(BaseModel):
    summary: ClusterSummary
    proposal: FolderAuditProposal
    report_path: Path
    input_tokens: int = 0
    output_tokens: int = 0
