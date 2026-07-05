from datetime import UTC, date, datetime

from src.brief.renderer import render_brief
from src.models.brief_models import BriefThreadSummary, FilingProposal, MorningBrief
from src.models.email_models import UrgencyBand


def make_brief(
    threads: list[BriefThreadSummary] | None = None,
    proposals: list[FilingProposal] | None = None,
) -> MorningBrief:
    return MorningBrief(
        brief_date=date(2026, 7, 4),
        account_email="owner@example.com",
        profile_id="consulting",
        persona_display_name="Consulting",
        lookback_hours=24,
        generated_at=datetime(2026, 7, 4, 6, 30, tzinfo=UTC),
        threads=threads or [],
        proposals=proposals or [],
        classified_now=len(threads or []),
        previously_classified=0,
    )


def make_thread(thread_id: str, subject: str, urgency: UrgencyBand) -> BriefThreadSummary:
    return BriefThreadSummary(
        thread_id=thread_id,
        subject=subject,
        senders=["client@example.com"],
        profile_id="consulting",
        urgency=urgency,
        message_count=2,
        latest_at=datetime(2026, 7, 4, 6, 0, tzinfo=UTC),
    )


def test_renders_bands_in_priority_order_and_omits_empty_bands() -> None:
    threads = [
        make_thread("t-low", "Newsletter", UrgencyBand.LOW),
        make_thread("t-crit", "Contract deadline today", UrgencyBand.CRITICAL),
    ]

    markdown = render_brief(make_brief(threads=threads))

    assert markdown.startswith("# Morning Brief - 2026-07-04")
    assert markdown.index("## Critical") < markdown.index("## Low")
    assert "## High" not in markdown
    assert "## Normal" not in markdown
    assert "**Contract deadline today**" in markdown
    assert "2 messages" in markdown
    assert "[consulting]" in markdown
    assert "classified now" in markdown


def test_renders_proposals_with_stable_ids() -> None:
    proposal = FilingProposal(
        proposal_id="abc123def456",
        message_id="row-0001",
        subject="Contract deadline today",
        urgency=UrgencyBand.CRITICAL,
        proposed_path=["Review"],
        requires_review=True,
        rationale="No human-approved filing rule is available.",
    )

    markdown = render_brief(make_brief(proposals=[proposal]))

    assert "## Filing proposals" in markdown
    assert "`abc123def456`" in markdown
    assert "[critical] Contract deadline today -> Review" in markdown
    assert "inboxmind review" in markdown


def test_empty_brief_renders_calm_message() -> None:
    markdown = render_brief(make_brief())

    assert "No new mail in this window." in markdown
    assert "No filing proposals in this window." in markdown
    assert "## Critical" not in markdown
