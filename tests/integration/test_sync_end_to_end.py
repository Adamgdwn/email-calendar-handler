"""End-to-end sync through fakes: Graph delta pages -> mapping -> dedupe ->
encryption -> table gateway. Proves the chunk 8 done criteria without any
network or real mailbox data.
"""

from __future__ import annotations

from src.ingestion.graph_delta import build_initial_delta_url
from src.sync_service import run_sync
from src.utils.encryption import FieldEncryptor
from tests.fakes import (
    FakeTableGateway,
    ScriptedGraphTransport,
    empty_calendar_script,
    graph_event,
    graph_message,
    make_consent,
    make_token,
    removed_message,
    todays_calendar_url,
    todays_event_time,
)

INITIAL_URL = build_initial_delta_url()
DELTA_LINK_ONE = "https://graph.microsoft.com/v1.0/delta?token=one"
DELTA_LINK_TWO = "https://graph.microsoft.com/v1.0/delta?token=two"
CALENDAR_URL = todays_calendar_url()


def make_encryptor() -> FieldEncryptor:
    return FieldEncryptor(FieldEncryptor.generate_key())


def test_first_sync_is_full_and_second_is_incremental() -> None:
    gateway = FakeTableGateway()
    encryptor = make_encryptor()
    transport = ScriptedGraphTransport(
        {
            INITIAL_URL: {
                "value": [
                    graph_message("m-0001", body="Body one"),
                    graph_message("m-0002", conversation_id="conv-0002", body="Body two"),
                ],
                "@odata.deltaLink": DELTA_LINK_ONE,
            },
            DELTA_LINK_ONE: {
                "value": [graph_message("m-0003", body="Body three")],
                "@odata.deltaLink": DELTA_LINK_TWO,
            },
            **empty_calendar_script(),
        }
    )
    consents = [make_consent()]

    first = run_sync(
        token=make_token(),
        transport=transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=consents,
    )
    second = run_sync(
        token=make_token(),
        transport=transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=consents,
    )

    assert first.full_sync is True
    assert first.resynced is False
    assert first.fetched == 2
    assert first.inserted == 2
    assert first.consents_uploaded == 1
    assert second.full_sync is False
    assert second.resynced is False
    assert second.inserted == 1
    assert second.consents_uploaded == 0
    assert first.calendar_events_stored == 0
    assert first.calendar_days == 1
    assert transport.requested_urls == [
        INITIAL_URL,
        CALENDAR_URL,
        DELTA_LINK_ONE,
        CALENDAR_URL,
    ]
    assert transport.seen_headers[0]["Authorization"] == "Bearer synthetic-access-token"

    emails = gateway.tables["emails"]
    assert len(emails) == 3
    stored_one = next(row for row in emails if row["provider_message_id"] == "m-0001")
    assert stored_one["body_ciphertext"] != "Body one"
    assert encryptor.decrypt_text(stored_one["body_ciphertext"]) == "Body one"
    assert all("body_text" not in row for row in emails)

    threads = gateway.tables["threads"]
    assert {row["provider_thread_id"] for row in threads} == {"conv-0001", "conv-0002"}
    stored_three = next(row for row in emails if row["provider_message_id"] == "m-0003")
    assert stored_three["thread_id"] == stored_one["thread_id"]

    assert len(gateway.tables["personas"]) == 1
    assert len(gateway.tables["accounts"]) == 1
    assert len(gateway.tables["account_consents"]) == 1
    checkpoints = gateway.tables["account_sync_checkpoints"]
    assert len(checkpoints) == 1
    assert checkpoints[0]["graph_delta_link"] == DELTA_LINK_TWO


def test_duplicate_ids_and_body_hashes_skipped_within_batch_and_across_runs() -> None:
    gateway = FakeTableGateway()
    encryptor = make_encryptor()
    transport = ScriptedGraphTransport(
        {
            INITIAL_URL: {
                "value": [
                    graph_message("m-1001", body="Repeated body"),
                    graph_message("m-1001", body="Repeated body"),
                    graph_message("m-1002", conversation_id="conv-0002", body="Repeated body"),
                    graph_message("m-1003", conversation_id="conv-0003", body="Unique body"),
                ],
                "@odata.deltaLink": DELTA_LINK_ONE,
            },
            DELTA_LINK_ONE: {
                "value": [graph_message("m-1001", body="Repeated body")],
                "@odata.deltaLink": DELTA_LINK_TWO,
            },
            **empty_calendar_script(),
        }
    )

    first = run_sync(
        token=make_token(),
        transport=transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[],
    )
    second = run_sync(
        token=make_token(),
        transport=transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[],
    )

    assert first.fetched == 4
    assert first.inserted == 2
    assert first.skipped_duplicates == 2
    assert second.fetched == 1
    assert second.inserted == 0
    assert second.skipped_duplicates == 1
    assert len(gateway.tables["emails"]) == 2


def test_stale_delta_state_triggers_explicit_resync() -> None:
    gateway = FakeTableGateway()
    encryptor = make_encryptor()
    first_transport = ScriptedGraphTransport(
        {
            INITIAL_URL: {
                "value": [graph_message("m-2001")],
                "@odata.deltaLink": DELTA_LINK_ONE,
            },
            **empty_calendar_script(),
        }
    )
    run_sync(
        token=make_token(),
        transport=first_transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[],
    )

    stale_transport = ScriptedGraphTransport(
        {
            DELTA_LINK_ONE: {
                "error": {"code": "SyncStateNotFound", "message": "synthetic stale state"}
            },
            INITIAL_URL: {
                "value": [
                    graph_message("m-2001"),
                    graph_message("m-2002", conversation_id="conv-0002", body="Second body"),
                ],
                "@odata.deltaLink": DELTA_LINK_TWO,
            },
            **empty_calendar_script(),
        }
    )
    report = run_sync(
        token=make_token(),
        transport=stale_transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[],
    )

    assert report.resynced is True
    assert report.full_sync is True
    assert report.inserted == 1
    assert report.skipped_duplicates == 1
    # The stale error must not burn transport retries; calendar follows mail.
    assert stale_transport.requested_urls == [DELTA_LINK_ONE, INITIAL_URL, CALENDAR_URL]
    checkpoints = gateway.tables["account_sync_checkpoints"]
    assert len(checkpoints) == 1
    assert checkpoints[0]["graph_delta_link"] == DELTA_LINK_TWO


def test_deleted_upstream_messages_are_reported_not_stored() -> None:
    gateway = FakeTableGateway()
    encryptor = make_encryptor()
    transport = ScriptedGraphTransport(
        {
            INITIAL_URL: {
                "value": [graph_message("m-3001"), removed_message("m-3002")],
                "@odata.deltaLink": DELTA_LINK_ONE,
            },
            **empty_calendar_script(),
        }
    )

    report = run_sync(
        token=make_token(),
        transport=transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[],
    )

    assert report.fetched == 1
    assert report.deleted_upstream == 1
    assert len(gateway.tables["emails"]) == 1


def test_calendar_events_stored_and_replaced_across_syncs() -> None:
    gateway = FakeTableGateway()
    encryptor = make_encryptor()
    first_transport = ScriptedGraphTransport(
        {
            INITIAL_URL: {
                "value": [graph_message("m-4001")],
                "@odata.deltaLink": DELTA_LINK_ONE,
            },
            CALENDAR_URL: {
                "value": [
                    graph_event("evt-0001", subject="Standup"),
                    graph_event(
                        "evt-0002",
                        subject="Client review",
                        start=todays_event_time(18),
                        end=todays_event_time(19),
                    ),
                ]
            },
        }
    )

    first = run_sync(
        token=make_token(),
        transport=first_transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[],
    )

    assert first.calendar_events_stored == 2
    rows = gateway.tables["calendar_events"]
    assert {row["provider_event_id"] for row in rows} == {"evt-0001", "evt-0002"}
    account_id = gateway.tables["accounts"][0]["id"]
    assert all(row["account_id"] == account_id for row in rows)

    second_transport = ScriptedGraphTransport(
        {
            DELTA_LINK_ONE: {"value": [], "@odata.deltaLink": DELTA_LINK_TWO},
            CALENDAR_URL: {"value": [graph_event("evt-0001", subject="Standup (moved)")]},
        }
    )

    second = run_sync(
        token=make_token(),
        transport=second_transport,
        gateway=gateway,
        encryptor=encryptor,
        consent_records=[],
    )

    assert second.calendar_events_stored == 1
    rows = gateway.tables["calendar_events"]
    assert len(rows) == 1
    assert rows[0]["subject"] == "Standup (moved)"
