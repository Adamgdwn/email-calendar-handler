from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.memory.feedback_store import (
    FEEDBACK_TABLE,
    FILING_TARGET_TYPE,
    acceptance_stats,
    load_feedback,
    record_feedback,
)
from src.models.feedback_models import FeedbackDecision, FeedbackRecord
from tests.fakes import FakeTableGateway

BASE = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)


def record(
    decision: FeedbackDecision,
    seconds: int,
    *,
    target_type: str = FILING_TARGET_TYPE,
    path: str = "Clients/Acme",
) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id="pending",
        account_id="acct-1",
        target_type=target_type,
        target_id=f"p-{seconds}",
        decision=decision,
        created_at=BASE + timedelta(seconds=seconds),
        context={"path": path},
    )


def test_record_and_load_round_trip_oldest_first() -> None:
    gateway = FakeTableGateway()
    record_feedback(
        gateway,
        [
            record(FeedbackDecision.ACCEPT, 2),
            record(FeedbackDecision.REJECT, 0),
            record(FeedbackDecision.ACCEPT, 1),
        ],
    )

    loaded = load_feedback(gateway, "acct-1")

    assert [r.created_at for r in loaded] == [
        BASE,
        BASE + timedelta(seconds=1),
        BASE + timedelta(seconds=2),
    ]
    assert loaded[0].decision is FeedbackDecision.REJECT
    assert loaded[0].feedback_id == "row-0002"
    assert loaded[0].context == {"path": "Clients/Acme"}


def test_record_writes_decision_string_and_context() -> None:
    gateway = FakeTableGateway()
    written = record_feedback(gateway, [record(FeedbackDecision.MODIFY, 0)])

    assert written == 1
    row = gateway.rows(FEEDBACK_TABLE)[0]
    assert row["decision"] == "modify"
    assert row["target_type"] == FILING_TARGET_TYPE
    assert row["context"] == {"path": "Clients/Acme"}


def test_load_filters_by_target_type() -> None:
    gateway = FakeTableGateway()
    record_feedback(
        gateway,
        [
            record(FeedbackDecision.ACCEPT, 0),
            record(FeedbackDecision.ACCEPT, 1, target_type="draft"),
        ],
    )

    filing = load_feedback(gateway, "acct-1", target_type=FILING_TARGET_TYPE)

    assert len(filing) == 1
    assert filing[0].target_type == FILING_TARGET_TYPE


def test_acceptance_stats_counts_accepts_over_total() -> None:
    gateway = FakeTableGateway()
    record_feedback(
        gateway,
        [
            record(FeedbackDecision.ACCEPT, 0),
            record(FeedbackDecision.ACCEPT, 1),
            record(FeedbackDecision.ACCEPT, 2),
            record(FeedbackDecision.REJECT, 3),
        ],
    )

    stats = acceptance_stats(gateway, "acct-1")

    assert stats.total == 4
    assert stats.accepted == 3
    assert stats.rate == 0.75


def test_acceptance_stats_empty_is_zero() -> None:
    stats = acceptance_stats(FakeTableGateway(), "acct-1")

    assert stats.total == 0
    assert stats.rate == 0.0


def test_record_feedback_no_records_writes_nothing() -> None:
    gateway = FakeTableGateway()

    assert record_feedback(gateway, []) == 0
    assert gateway.rows(FEEDBACK_TABLE) == []
