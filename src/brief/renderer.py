"""Render the Morning Brief as markdown for terminal and file output.

Pure formatting only: no I/O, no persistence, no classification decisions.
"""

from __future__ import annotations

from src.models.brief_models import (
    URGENCY_ORDER,
    BriefThreadSummary,
    FilingAcceptanceStats,
    FilingProposal,
    MorningBrief,
)
from src.models.calendar_models import CalendarEvent
from src.models.email_models import UrgencyBand

_ATTENDEE_DISPLAY_CAP = 4
WRITE_SCOPE_GATE_RATE = 0.70

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
    lines.extend(["", "## Agenda", ""])
    if brief.events:
        lines.extend(_event_line(event) for event in brief.events)
    else:
        lines.append("No meetings today.")
    lines.append("")
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
        lines.append("Review these with `inboxmind review` (accept / modify / reject).")
        lines.extend(_proposal_line(proposal) for proposal in brief.proposals)
    else:
        lines.append("No filing proposals in this window.")
    lines.extend(["", "## Filing feedback", "", _acceptance_line(brief.acceptance)])
    lines.append("")
    return "\n".join(lines)


def _acceptance_line(stats: FilingAcceptanceStats) -> str:
    if stats.total == 0:
        return "No filing feedback yet; run `inboxmind review` to start the learning loop."
    gate = "open" if stats.rate >= WRITE_SCOPE_GATE_RATE else "closed"
    return (
        f"Filing acceptance: {stats.rate:.0%} ({stats.accepted}/{stats.total} reviewed). "
        f"Write-scope gate ({WRITE_SCOPE_GATE_RATE:.0%}) is {gate}."
    )


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
    line = (
        f"- **{thread.subject}** - {senders} "
        f"({thread.message_count} message{plural}, latest {latest}) [{thread.profile_id}]"
    )
    if thread.boost_reason:
        line += f" - {thread.boost_reason}"
    return line


def _event_line(event: CalendarEvent) -> str:
    if event.is_all_day:
        window = "All day:"
    else:
        window = f"{event.start.strftime('%H:%M')}-{event.end.strftime('%H:%M')}"
    subject = event.subject or "(no subject)"
    return f"- {window} **{subject}**{_event_details(event)}"


def _event_details(event: CalendarEvent) -> str:
    details = ""
    if event.attendees:
        shown = [attendee.name or attendee.email for attendee in event.attendees]
        overflow = len(shown) - _ATTENDEE_DISPLAY_CAP
        if overflow > 0:
            shown = shown[:_ATTENDEE_DISPLAY_CAP]
        people = ", ".join(shown)
        if overflow > 0:
            people += f" +{overflow} more"
        details += f" - with {people}"
    if event.location:
        details += f" ({event.location})"
    if event.online_meeting_url:
        details += f" - join: {event.online_meeting_url}"
    return details


def _proposal_line(proposal: FilingProposal) -> str:
    path = "/".join(proposal.proposed_path)
    return (
        f"- `{proposal.proposal_id}` [{proposal.urgency.value}] {proposal.subject} -> {path} "
        f"- {proposal.rationale}"
    )
