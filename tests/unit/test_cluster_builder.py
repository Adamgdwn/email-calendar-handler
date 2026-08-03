"""Unit tests for ClusterBuilder — fully deterministic, no I/O."""

from __future__ import annotations

from src.inbox_audit.cluster_builder import ClusterBuilder
from src.models.audit_models import FolderNode, MessageMetadataRow


def _row(
    domain: str,
    subject: str = "Test",
    folder_path: list[str] | None = None,
    month: str = "2025-01",
) -> MessageMetadataRow:
    return MessageMetadataRow(
        sender_domain=domain,
        subject_prefix=subject[:60],
        folder_path=folder_path or ["Inbox"],
        received_month=month,
    )


def _node(name: str, count: int = 0, children: list[FolderNode] | None = None) -> FolderNode:
    return FolderNode(
        folder_id=name.lower(),
        display_name=name,
        parent_id=None,
        message_count=count,
        child_folders=children or [],
    )


def test_total_messages_count() -> None:
    rows = [_row("a.com"), _row("b.com"), _row("c.com")]
    summary = ClusterBuilder().build(rows, [_node("Inbox")], "test@x.com", 6)
    assert summary.total_messages == 3


def test_total_folders_counts_children() -> None:
    tree = [_node("Inbox", children=[_node("Projects"), _node("Archive")])]
    summary = ClusterBuilder().build([], tree, "test@x.com", 6)
    assert summary.total_folders == 3  # Inbox + Projects + Archive


def test_build_folder_utilization() -> None:
    rows = [
        _row("a.com", folder_path=["Inbox"]),
        _row("b.com", folder_path=["Inbox"]),
        _row("c.com", folder_path=["Inbox", "Projects"]),
    ]
    summary = ClusterBuilder().build(rows, [], "test@x.com", 6)
    assert summary.folder_utilization["Inbox"] == 2
    assert summary.folder_utilization["Inbox/Projects"] == 1


def test_domain_clusters_top30_rollup() -> None:
    # 31 distinct domains → top 30 + "other"
    rows = [_row(f"domain{i}.com") for i in range(31)]
    summary = ClusterBuilder().build(rows, [], "test@x.com", 12)
    labels = [c.label for c in summary.domain_clusters]
    assert "other" in labels
    non_other = [c for c in summary.domain_clusters if c.label != "other"]
    assert len(non_other) == 30


def test_domain_clusters_under30_no_rollup() -> None:
    rows = [_row("a.com"), _row("b.com")]
    summary = ClusterBuilder().build(rows, [], "test@x.com", 12)
    labels = [c.label for c in summary.domain_clusters]
    assert "other" not in labels


def test_domain_cluster_message_count() -> None:
    rows = [_row("x.com")] * 5 + [_row("y.com")] * 2
    summary = ClusterBuilder().build(rows, [], "test@x.com", 12)
    by_label = {c.label: c for c in summary.domain_clusters}
    assert by_label["x.com"].message_count == 5
    assert by_label["y.com"].message_count == 2


def test_domain_cluster_sample_subjects_capped_at_5() -> None:
    rows = [_row("x.com", subject=f"Subject {i}") for i in range(10)]
    summary = ClusterBuilder().build(rows, [], "test@x.com", 12)
    xcom_cluster = next(c for c in summary.domain_clusters if c.label == "x.com")
    assert len(xcom_cluster.sample_subjects) == 5


def test_subject_keyword_clusters_excludes_stopwords() -> None:
    rows = [_row("a.com", subject="re invoice approval")]
    summary = ClusterBuilder().build(rows, [], "test@x.com", 12)
    labels = [c.label for c in summary.subject_keyword_clusters]
    assert "re" not in labels
    assert "invoice" in labels or "approval" in labels


def test_subject_keyword_clusters_top5_only() -> None:
    # 10 distinct keywords, each in one message
    words = [
        "alpha",
        "bravo",
        "charlie",
        "delta",
        "echo",
        "foxtrot",
        "golf",
        "hotel",
        "india",
        "juliet",
    ]
    rows = [_row("a.com", subject=w) for w in words]
    summary = ClusterBuilder().build(rows, [], "test@x.com", 12)
    assert len(summary.subject_keyword_clusters) == 5


def test_dominant_folder_picks_most_common() -> None:
    rows = [
        _row("x.com", folder_path=["Inbox"]),
        _row("x.com", folder_path=["Inbox"]),
        _row("x.com", folder_path=["Archive"]),
    ]
    summary = ClusterBuilder().build(rows, [], "test@x.com", 12)
    xcom = next(c for c in summary.domain_clusters if c.label == "x.com")
    assert xcom.dominant_folder == "Inbox"


def test_months_scanned_preserved() -> None:
    summary = ClusterBuilder().build([], [], "test@x.com", 9)
    assert summary.months_scanned == 9


def test_account_email_preserved() -> None:
    summary = ClusterBuilder().build([], [], "user@example.com", 12)
    assert summary.account_email == "user@example.com"
