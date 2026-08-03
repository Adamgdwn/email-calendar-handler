"""Unit tests for AuditRenderer — file content and terminal output."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.inbox_audit.audit_renderer import render_audit_report
from src.models.audit_models import (
    AuditReport,
    ClusterSummary,
    FolderAuditProposal,
    FolderNode,
    ProposedFolder,
)


def _make_proposal(account_email: str = "user@example.com") -> FolderAuditProposal:
    return FolderAuditProposal(
        account_email=account_email,
        generated_at=datetime(2025, 7, 5, 10, 0, 0, tzinfo=UTC),
        proposed_tree=[
            ProposedFolder(
                path=["Clients"],
                rationale="All client mail in one place",
                source_folders=["OldClients"],
                estimated_volume=50,
            ),
            ProposedFolder(
                path=["Finance"],
                rationale="Invoices and receipts",
                source_folders=[],
                estimated_volume=30,
            ),
        ],
        folders_to_retire=["OldClients", "Misc"],
        folders_to_keep=["Inbox", "Sent"],
        key_changes=["Consolidated 3 client folders", "Created Finance"],
        implementation_note="Move mail manually or use Outlook rules.",
    )


def _make_summary() -> ClusterSummary:
    return ClusterSummary(
        account_email="user@example.com",
        months_scanned=12,
        total_messages=200,
        total_folders=8,
        current_folder_tree=[
            FolderNode(
                folder_id="f1",
                display_name="Inbox",
                parent_id=None,
                message_count=100,
                child_folders=[
                    FolderNode(
                        folder_id="f2",
                        display_name="Projects",
                        parent_id="f1",
                        message_count=40,
                    )
                ],
            )
        ],
        domain_clusters=[],
        folder_utilization={},
        subject_keyword_clusters=[],
    )


@pytest.fixture()
def report(tmp_path: Path) -> AuditReport:
    return AuditReport(
        summary=_make_summary(),
        proposal=_make_proposal(),
        report_path=tmp_path / "audits" / "audit-2025-07-05.md",
        input_tokens=800,
        output_tokens=350,
    )


def test_render_creates_file(report: AuditReport) -> None:
    render_audit_report(report)
    assert report.report_path.exists()


def test_render_creates_parent_directory(report: AuditReport) -> None:
    assert not report.report_path.parent.exists()
    render_audit_report(report)
    assert report.report_path.parent.exists()


def test_render_file_contains_required_sections(report: AuditReport) -> None:
    render_audit_report(report)
    content = report.report_path.read_text(encoding="utf-8")
    assert "## Current Structure" in content
    assert "## Proposed Structure" in content
    assert "## Migration Notes" in content
    assert "## Folders to Retire" in content
    assert "## Folders to Keep" in content


def test_render_file_contains_account_email(report: AuditReport) -> None:
    render_audit_report(report)
    content = report.report_path.read_text(encoding="utf-8")
    assert "user@example.com" in content


def test_render_file_contains_proposed_folders(report: AuditReport) -> None:
    render_audit_report(report)
    content = report.report_path.read_text(encoding="utf-8")
    assert "Clients" in content
    assert "Finance" in content


def test_render_file_contains_folders_to_retire(report: AuditReport) -> None:
    render_audit_report(report)
    content = report.report_path.read_text(encoding="utf-8")
    assert "OldClients" in content
    assert "Misc" in content


def test_render_file_contains_current_folder_tree(report: AuditReport) -> None:
    render_audit_report(report)
    content = report.report_path.read_text(encoding="utf-8")
    assert "Inbox" in content
    assert "Projects" in content


def test_render_terminal_shows_key_changes(
    report: AuditReport, capsys: pytest.CaptureFixture[str]
) -> None:
    render_audit_report(report)
    captured = capsys.readouterr()
    assert "Consolidated 3 client folders" in captured.out
    assert "Created Finance" in captured.out


def test_render_terminal_shows_token_cost(
    report: AuditReport, capsys: pytest.CaptureFixture[str]
) -> None:
    render_audit_report(report)
    captured = capsys.readouterr()
    assert "800" in captured.out
    assert "350" in captured.out


def test_render_terminal_shows_report_path(
    report: AuditReport, capsys: pytest.CaptureFixture[str]
) -> None:
    render_audit_report(report)
    captured = capsys.readouterr()
    assert "audit-2025-07-05.md" in captured.out


def test_render_terminal_shows_proposed_tree(
    report: AuditReport, capsys: pytest.CaptureFixture[str]
) -> None:
    render_audit_report(report)
    captured = capsys.readouterr()
    assert "Clients" in captured.out
    assert "Finance" in captured.out
