"""Audit report renderer: Markdown file at INBOXMIND_HOME/audits/ + terminal summary."""

from __future__ import annotations

from src.models.audit_models import AuditReport


def render_audit_report(report: AuditReport) -> None:
    """Write the Markdown file and print the terminal summary."""
    _write_markdown(report)
    _print_terminal_summary(report)


def _write_markdown(report: AuditReport) -> None:
    proposal = report.proposal
    summary = report.summary
    lines: list[str] = [
        "# InboxMind Inbox Audit",
        "",
        f"**Account:** {proposal.account_email}  ",
        f"**Generated:** {proposal.generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
        (
            f"**Period:** {summary.months_scanned} months — "
            f"{summary.total_messages:,} messages across {summary.total_folders} folders"
        ),
        "",
        "---",
        "",
        "## Current Structure",
        "",
    ]
    for node in summary.current_folder_tree:
        lines.append(f"- **{node.display_name}** ({node.message_count} messages)")
        for child in node.child_folders:
            lines.append(f"  - {child.display_name} ({child.message_count} messages)")

    lines += ["", "## Proposed Structure", ""]
    for folder in proposal.proposed_tree:
        path_str = " / ".join(folder.path)
        lines.append(f"- **{path_str}** (~{folder.estimated_volume} messages)")
        lines.append(f"  _{folder.rationale}_")
        if folder.source_folders:
            src = ", ".join(folder.source_folders)
            lines.append(f"  Consolidates: {src}")

    lines += ["", "## Migration Notes", ""]
    for change in proposal.key_changes:
        lines.append(f"- {change}")
    lines += ["", proposal.implementation_note, "", "## Folders to Retire", ""]
    for folder_name in proposal.folders_to_retire:
        lines.append(f"- {folder_name}")
    lines += ["", "## Folders to Keep", ""]
    for folder_name in proposal.folders_to_keep:
        lines.append(f"- {folder_name}")

    report.report_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    report.report_path.write_text("\n".join(lines), encoding="utf-8")


def _print_terminal_summary(report: AuditReport) -> None:
    proposal = report.proposal
    summary = report.summary
    print(f"\n  ── INBOX AUDIT — {proposal.account_email} ──")
    print(
        f"  {summary.total_messages:,} messages · {summary.total_folders} folders"
        f" · {summary.months_scanned} months scanned"
    )
    print(f"\n  Proposed structure ({len(proposal.proposed_tree)} folders):")
    for folder in proposal.proposed_tree:
        path_str = " / ".join(folder.path)
        print(f"    {path_str} (~{folder.estimated_volume})")
    print("\n  Key changes:")
    for change in proposal.key_changes:
        print(f"    · {change}")
    print(f"\n  ── {report.input_tokens} tokens in · {report.output_tokens} tokens out ──")
    print(f"\n  Report: {report.report_path}")
