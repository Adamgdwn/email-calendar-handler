"""Render the Morning Brief as markdown for terminal and file output.

Pure formatting only: no I/O, no persistence, no classification decisions.
"""

from __future__ import annotations

from src.models.brief_models import (
    URGENCY_ORDER,
    BriefThreadSummary,
    FilingAcceptanceStats,
    FilingProposal,
    LLMAssistStats,
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
    lines: list[str] = []

    # Header — natural date, no developer-speak
    day = brief.brief_date.strftime("%a %b %-d")
    generated = brief.generated_at.strftime("%H:%M %Z")
    lines.append(f"# Morning Brief — {day}")
    lines.append(
        f"{brief.account_email} · {brief.persona_display_name} · "
        f"last {brief.lookback_hours} h · {generated}"
    )
    lines.extend(["", _opener(brief), ""])

    # Agenda section — only rendered when there are events
    if brief.events:
        lines.extend(["## Agenda", ""])
        lines.extend(_event_line(event) for event in brief.events)
        lines.append("")

    # Mail sections with proposals inlined under each thread
    proposals_by_subject = _group_proposals_by_subject(brief.proposals)
    for band in URGENCY_ORDER:
        section = [t for t in brief.threads if t.urgency == band]
        if not section:
            continue
        lines.extend([f"## {_BAND_TITLES[band]}", ""])
        for thread in section:
            lines.append(_thread_line(thread))
            for prop in proposals_by_subject.get(thread.subject, []):
                path = "/".join(prop.proposed_path)
                lines.append(f"  → Proposal: {path} · `{prop.proposal_id}`")
        lines.append("")

    if not brief.threads:
        lines.extend(["No new mail in this window.", ""])

    lines.append(_acceptance_line(brief.acceptance))
    if brief.llm_assist is not None and brief.llm_assist.enabled:
        lines.append(_llm_assist_line(brief.llm_assist))
    lines.append("")
    return "\n".join(lines)


def _opener(brief: MorningBrief) -> str:
    n_events = len(brief.events)
    n_threads = len(brief.threads)

    if n_events == 0:
        calendar = "No meetings today."
    elif n_events == 1:
        calendar = "One meeting today."
    else:
        calendar = f"{n_events} meetings today."

    if n_threads == 0:
        mail = "Inbox is clear."
    else:
        critical = sum(1 for t in brief.threads if t.urgency == UrgencyBand.CRITICAL)
        high = sum(1 for t in brief.threads if t.urgency == UrgencyBand.HIGH)
        if critical > 0:
            s = "" if critical == 1 else "s"
            mail = f"{critical} critical thread{s} need{'s' if critical == 1 else ''} attention."
        elif high > 0:
            s = "" if high == 1 else "s"
            mail = f"{high} high-priority thread{s} to review."
        else:
            s = "thread" if n_threads == 1 else "threads"
            mail = f"Quiet inbox — {n_threads} low-priority {s}."

    return f"{calendar} {mail}"


def _group_proposals_by_subject(
    proposals: list[FilingProposal],
) -> dict[str, list[FilingProposal]]:
    result: dict[str, list[FilingProposal]] = {}
    for proposal in proposals:
        result.setdefault(proposal.subject, []).append(proposal)
    return result


def _acceptance_line(stats: FilingAcceptanceStats) -> str:
    if stats.total == 0:
        return "No filing feedback yet — run `inboxmind review` to start the learning loop."
    gate = "open" if stats.rate >= WRITE_SCOPE_GATE_RATE else "closed"
    return (
        f"Filing acceptance: {stats.rate:.0%} ({stats.accepted}/{stats.total} reviewed). "
        f"Write-scope gate ({WRITE_SCOPE_GATE_RATE:.0%}) is {gate}."
    )


def _thread_line(thread: BriefThreadSummary) -> str:
    senders = ", ".join(thread.senders)
    latest = thread.latest_at.strftime("%H:%M")
    line = f"- **{thread.subject}** · {senders} · {latest}"
    if thread.message_count > 1:
        line += f" ({thread.message_count} messages)"
    if thread.boost_reason:
        line += f" — {thread.boost_reason}"
    return line


def _llm_assist_line(stats: LLMAssistStats) -> str:
    parts = [
        f"LLM assist: {stats.assisted_this_run} email(s) this run, "
        f"{stats.tokens_used_today} tokens today."
    ]
    if stats.rolling_total > 0:
        det = f"{stats.det_accept_rate:.0%}" if stats.det_accept_rate is not None else "n/a"
        llm = f"{stats.llm_accept_rate:.0%}" if stats.llm_accept_rate is not None else "n/a"
        parts.append(f"Accuracy rolling {stats.rolling_total}: det {det} / llm {llm}.")
    return " ".join(parts)


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
