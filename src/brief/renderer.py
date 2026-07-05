"""Render the Morning Brief as markdown for terminal and file output.

Pure formatting only: no I/O, no persistence, no classification decisions.
"""

from __future__ import annotations

from src.models.brief_models import URGENCY_ORDER, BriefThreadSummary, FilingProposal, MorningBrief
from src.models.email_models import UrgencyBand

_BAND_TITLES: dict[UrgencyBand, str] = {
    UrgencyBand.CRITICAL: "Critical",
    UrgencyBand.HIGH: "High",
    UrgencyBand.NORMAL: "Normal",
    UrgencyBand.LOW: "Low",
}


def render_brief(brief: MorningBrief) -> str:
    lines: list[str] = [f"# Morning Brief - {brief.brief_date.isoformat()}", ""]
    lines.append(
        f"Account: {brief.account_email} - {brief.persona_display_name} ({brief.profile_id})"
    )
    lines.append(
        f"Window: last {brief.lookback_hours} hours, generated "
        f"{brief.generated_at.strftime('%Y-%m-%d %H:%M %Z')}"
    )
    lines.append(_triage_line(brief))
    for band in URGENCY_ORDER:
        section = [thread for thread in brief.threads if thread.urgency == band]
        if not section:
            continue
        lines.extend(["", f"## {_BAND_TITLES[band]}", ""])
        lines.extend(_thread_line(thread) for thread in section)
    if not brief.threads:
        lines.extend(["", "No new mail in this window."])
    lines.extend(["", "## Filing proposals", ""])
    if brief.proposals:
        lines.append("Every proposal awaits review; `inboxmind review` arrives in chunk 11.")
        lines.extend(_proposal_line(proposal) for proposal in brief.proposals)
    else:
        lines.append("No filing proposals in this window.")
    lines.append("")
    return "\n".join(lines)


def _triage_line(brief: MorningBrief) -> str:
    total_messages = sum(thread.message_count for thread in brief.threads)
    return (
        f"Triage: {len(brief.threads)} threads, {total_messages} messages - "
        f"{brief.classified_now} classified now, "
        f"{brief.previously_classified} already classified"
    )


def _thread_line(thread: BriefThreadSummary) -> str:
    plural = "s" if thread.message_count != 1 else ""
    senders = ", ".join(thread.senders)
    latest = thread.latest_at.strftime("%H:%M")
    return (
        f"- **{thread.subject}** - {senders} "
        f"({thread.message_count} message{plural}, latest {latest}) [{thread.profile_id}]"
    )


def _proposal_line(proposal: FilingProposal) -> str:
    path = "/".join(proposal.proposed_path)
    return (
        f"- `{proposal.proposal_id}` [{proposal.urgency.value}] {proposal.subject} -> {path} "
        f"- {proposal.rationale}"
    )
