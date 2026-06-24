"""Provider clients and provider-neutral ingestion helpers."""

from src.ingestion.graph_delta import GraphDeltaCheckpoint, GraphDeltaSyncResult
from src.ingestion.provider_contracts import (
    ProviderEmailAdapter,
    ProviderSyncCheckpoint,
    ProviderSyncResult,
)
from src.ingestion.thread_assembler import assemble_email_threads

__all__ = [
    "GraphDeltaCheckpoint",
    "GraphDeltaSyncResult",
    "ProviderEmailAdapter",
    "ProviderSyncCheckpoint",
    "ProviderSyncResult",
    "assemble_email_threads",
]
