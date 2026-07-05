"""Review loop end to end against the in-memory gateway (scripted prompter)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet

from src.memory.account_store import ensure_account
from src.memory.feedback_store import FEEDBACK_TABLE
from src.models.brief_models import FilingProposal
from src.models.email_models import Provider
from src.models.feedback_models import FeedbackDecision
from src.personas.loader import load_personas
from src.review_service import ReviewInput, ReviewReport, run_review
from src.utils.encryption import FieldEncryptor
from tests.fakes import FakeTableGateway

NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)


class ScriptedPrompter:
    """Answers proposals by subject; everything else takes the default."""

    def __init__(
        self, by_subject: dict[str, ReviewInput] | None = None, default: ReviewInput | None = None
    ) -> None:
        self._by_subject = by_subject or {}
        self._default = default or ReviewInput()
        self.seen: list[str] = []

    def review(self, proposal: FilingProposal) -> ReviewInput:
        self.seen.append(proposal.subject)
        return self._by_subject.get(proposal.subject, self._default)


def build_encryptor() -> FieldEncryptor:
    return FieldEncryptor(Fernet.generate_key())


def seed(gateway: FakeTableGateway, encryptor: FieldEncryptor, subjects: list[str]) -> str:
    account_id = ensure_account(
        gateway,
        provider=Provider.MICROSOFT_GRAPH,
        primary_email="owner@example.com",
        display_name="Owner",
        org_type="organizational",
        scopes=["User.Read", "Mail.Read"],
    )
    gateway.insert_rows(
        "emails",
        [
            {
                "account_id": account_id,
                "thread_id": f"thread-{index}",
                "provider_message_id": f"m-{index}",
                "sender_email": "client@clientfirm.example",
                "subject": subject,
                "body_ciphertext": encryptor.encrypt_text("Synthetic body."),
                "body_hash": f"hash-{index}",
                "message_timestamp": (NOW - timedelta(hours=1)).isoformat(),
                "labels": ["INBOX"],
                "urgency": None,
                "classification": {},
            }
            for index, subject in enumerate(subjects)
        ],
    )
    return account_id


def run(
    gateway: FakeTableGateway, encryptor: FieldEncryptor, prompter: ScriptedPrompter
) -> ReviewReport:
    return run_review(
        gateway=gateway,
        encryptor=encryptor,
        personas=load_personas(),
        prompter=prompter,
        profile_override="consulting",
        lookback_hours=24,
        now=NOW,
    )


def test_three_accepts_of_one_path_confirm_a_rule_without_approving_it() -> None:
    gateway = FakeTableGateway()
    encryptor = build_encryptor()
    seed(gateway, encryptor, ["First", "Second", "Third"])
    prompter = ScriptedPrompter(default=ReviewInput(decision=FeedbackDecision.ACCEPT))

    report = run(gateway, encryptor, prompter)

    assert report.reviewed == 3
    assert report.accepted == 3
    assert report.feedback_recorded == 3
    assert len(gateway.rows(FEEDBACK_TABLE)) == 3
    assert report.promoted_paths == ["Review"]
    assert report.acceptance.total == 3
    assert report.acceptance.rate == 1.0

    rules = gateway.rows("filing_rules")
    assert len(rules) == 1
    assert rules[0]["status"] == "confirmed"
    assert rules[0]["created_by"] == "learning_agent"
    assert rules[0]["human_approved"] is False


def test_mixed_decisions_record_feedback_and_stay_provisional() -> None:
    gateway = FakeTableGateway()
    encryptor = build_encryptor()
    seed(gateway, encryptor, ["Alpha", "Beta"])
    prompter = ScriptedPrompter(
        by_subject={
            "Alpha": ReviewInput(decision=FeedbackDecision.ACCEPT),
            "Beta": ReviewInput(
                decision=FeedbackDecision.MODIFY, modified_path=["Clients", "Beta"]
            ),
        }
    )

    report = run(gateway, encryptor, prompter)

    assert report.accepted == 1
    assert report.modified == 1
    assert report.reviewed == 2
    assert report.promoted_paths == []
    assert report.acceptance.total == 2
    assert report.acceptance.accepted == 1

    beta_rows = [
        row for row in gateway.rows(FEEDBACK_TABLE) if row["context"]["path"] == "Clients/Beta"
    ]
    assert len(beta_rows) == 1
    assert beta_rows[0]["decision"] == "modify"


def test_skipping_every_proposal_records_nothing() -> None:
    gateway = FakeTableGateway()
    encryptor = build_encryptor()
    seed(gateway, encryptor, ["Alpha", "Beta"])
    prompter = ScriptedPrompter(default=ReviewInput())

    report = run(gateway, encryptor, prompter)

    assert report.reviewed == 0
    assert report.feedback_recorded == 0
    assert report.rules_written == 0
    assert gateway.rows(FEEDBACK_TABLE) == []
    assert prompter.seen == ["Alpha", "Beta"]
