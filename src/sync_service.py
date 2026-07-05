"""End-to-end mailbox sync: Graph delta, dedupe, encryption, Supabase persistence.

`inboxmind sync` calls `run_sync`; tests drive it with a fake transport and a
fake table gateway. Stale delta state is an explicit resync, never a silent
retry.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from src.ingestion.graph_delta import (
    DEFAULT_MAIL_FOLDER_ID,
    GraphDeltaCheckpoint,
    GraphDeltaStateExpiredError,
    GraphDeltaSyncResult,
    GraphTransport,
    run_graph_delta_sync,
)
from src.ingestion.graph_token_cache import GraphAuthError, GraphTokenResult
from src.ingestion.graph_transport import GraphTransportError
from src.ingestion.provider_contracts import ProviderSyncCheckpoint
from src.memory.account_store import DEFAULT_PROFILE_ID, ensure_account, upload_consents
from src.memory.checkpoint_store import CheckpointStore
from src.memory.email_store import SupabaseEmailStore, prepare_encrypted_email_record
from src.memory.supabase_client import TableGateway
from src.models.auth_models import OAuthConsentRecord
from src.models.email_models import AccountContext, EmailAddress, Provider
from src.utils.encryption import FieldEncryptor
from src.utils.rate_limiter import retry_provider_call


class SyncReport(BaseModel):
    account_email: str
    mail_folder_id: str
    full_sync: bool
    resynced: bool
    fetched: int
    inserted: int
    skipped_duplicates: int
    deleted_upstream: int
    consents_uploaded: int


def run_sync(
    *,
    token: GraphTokenResult,
    transport: GraphTransport,
    gateway: TableGateway,
    encryptor: FieldEncryptor,
    consent_records: list[OAuthConsentRecord],
    mail_folder_id: str = DEFAULT_MAIL_FOLDER_ID,
) -> SyncReport:
    _require_email_subject(token)
    account_id = ensure_account(
        gateway,
        provider=Provider.MICROSOFT_GRAPH,
        primary_email=token.subject,
        display_name=token.subject,
        org_type=token.account_type or "unknown",
        scopes=list(token.scopes),
    )
    consents_uploaded = upload_consents(gateway, account_id=account_id, records=consent_records)

    checkpoint_store = CheckpointStore(gateway)
    stored = checkpoint_store.load(
        account_id=account_id, provider=Provider.MICROSOFT_GRAPH, mail_folder_id=mail_folder_id
    )
    full_sync = stored.graph_delta_link is None
    resynced = False
    try:
        result = _run_delta(transport, token, account_id, mail_folder_id, stored.graph_delta_link)
    except GraphDeltaStateExpiredError:
        checkpoint_store.clear(
            account_id=account_id, provider=Provider.MICROSOFT_GRAPH, mail_folder_id=mail_folder_id
        )
        result = _run_delta(transport, token, account_id, mail_folder_id, None)
        full_sync = True
        resynced = True

    account_context = AccountContext(
        account_id=account_id,
        profile_id=DEFAULT_PROFILE_ID,
        provider=Provider.MICROSOFT_GRAPH,
        display_name=token.subject,
        primary_email=token.subject,
        org_type=token.account_type or "unknown",
    )
    records = [
        prepare_encrypted_email_record(account_context, email, encryptor) for email in result.emails
    ]
    batch = SupabaseEmailStore(gateway).store_batch(account_id, records)
    checkpoint_store.save(
        ProviderSyncCheckpoint(
            account_id=account_id,
            provider=Provider.MICROSOFT_GRAPH,
            mail_folder_id=mail_folder_id,
            graph_delta_link=result.delta_link,
        )
    )
    return SyncReport(
        account_email=token.subject,
        mail_folder_id=mail_folder_id,
        full_sync=full_sync,
        resynced=resynced,
        fetched=len(result.emails),
        inserted=batch.inserted,
        skipped_duplicates=batch.skipped_duplicates,
        deleted_upstream=len(result.deleted_message_ids),
        consents_uploaded=consents_uploaded,
    )


def _require_email_subject(token: GraphTokenResult) -> None:
    try:
        EmailAddress(address=token.subject)
    except ValidationError as exc:
        msg = (
            "signed-in account has no usable email address claim; "
            "reconnect with `inboxmind connect`"
        )
        raise GraphAuthError(msg) from exc


def _run_delta(
    transport: GraphTransport,
    token: GraphTokenResult,
    account_id: str,
    mail_folder_id: str,
    delta_link: str | None,
) -> GraphDeltaSyncResult:
    checkpoint = GraphDeltaCheckpoint(
        account_id=account_id, mail_folder_id=mail_folder_id, delta_link=delta_link
    )
    return retry_provider_call(
        lambda: run_graph_delta_sync(
            transport,
            access_token=token.access_token.get_secret_value(),
            checkpoint=checkpoint,
        ),
        retry_exception_types=(GraphTransportError,),
    )
