from __future__ import annotations

from src.ingestion.provider_contracts import ProviderSyncCheckpoint
from src.memory.checkpoint_store import CHECKPOINTS_TABLE, CheckpointStore
from src.models.email_models import Provider
from tests.fakes import FakeTableGateway

ACCOUNT_ID = "row-account-0001"
DELTA_LINK_ONE = "https://graph.microsoft.com/v1.0/delta?token=one"
DELTA_LINK_TWO = "https://graph.microsoft.com/v1.0/delta?token=two"


def make_checkpoint(delta_link: str | None) -> ProviderSyncCheckpoint:
    return ProviderSyncCheckpoint(
        account_id=ACCOUNT_ID,
        provider=Provider.MICROSOFT_GRAPH,
        mail_folder_id="inbox",
        graph_delta_link=delta_link,
    )


def load(store: CheckpointStore) -> ProviderSyncCheckpoint:
    return store.load(
        account_id=ACCOUNT_ID, provider=Provider.MICROSOFT_GRAPH, mail_folder_id="inbox"
    )


def test_load_returns_empty_checkpoint_when_absent() -> None:
    store = CheckpointStore(FakeTableGateway())

    checkpoint = load(store)

    assert checkpoint.graph_delta_link is None
    assert checkpoint.account_id == ACCOUNT_ID
    assert checkpoint.provider is Provider.MICROSOFT_GRAPH


def test_save_round_trips_and_upserts_a_single_row() -> None:
    gateway = FakeTableGateway()
    store = CheckpointStore(gateway)

    store.save(make_checkpoint(DELTA_LINK_ONE))
    store.save(make_checkpoint(DELTA_LINK_TWO))

    assert load(store).graph_delta_link == DELTA_LINK_TWO
    assert len(gateway.tables[CHECKPOINTS_TABLE]) == 1
    assert gateway.tables[CHECKPOINTS_TABLE][0]["provider"] == "microsoft_graph"


def test_clear_resets_delta_state_but_keeps_the_row() -> None:
    gateway = FakeTableGateway()
    store = CheckpointStore(gateway)
    store.save(make_checkpoint(DELTA_LINK_ONE))

    store.clear(account_id=ACCOUNT_ID, provider=Provider.MICROSOFT_GRAPH, mail_folder_id="inbox")

    assert load(store).graph_delta_link is None
    assert len(gateway.tables[CHECKPOINTS_TABLE]) == 1
