"""Tests for multi-account brief rendering and service logic (chunk 15)."""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.brief.renderer import render_brief, render_multi_brief
from src.brief_service import BriefDataError, PersonaSelectionError, run_multi_brief
from src.cli import TOKEN_CACHE_FILENAME, _token_cache_filename, main
from src.memory.account_store import ensure_account, link_account_persona
from src.models.brief_models import (
    BriefThreadSummary,
    FilingAcceptanceStats,
    MorningBrief,
    MultiBrief,
)
from src.models.email_models import Provider, UrgencyBand
from src.personas.loader import load_personas
from src.utils.encryption import FieldEncryptor
from tests.fakes import FakeTableGateway

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_section(
    account_email: str,
    persona_display_name: str,
    profile_id: str,
    threads: list[BriefThreadSummary] | None = None,
) -> MorningBrief:
    return MorningBrief(
        brief_date=date(2026, 8, 3),
        account_email=account_email,
        profile_id=profile_id,
        persona_display_name=persona_display_name,
        lookback_hours=24,
        generated_at=datetime(2026, 8, 3, 7, 0, tzinfo=UTC),
        events=[],
        threads=threads or [],
        proposals=[],
        acceptance=FilingAcceptanceStats(),
        classified_now=0,
        previously_classified=0,
    )


def _make_thread(subject: str, urgency: UrgencyBand) -> BriefThreadSummary:
    return BriefThreadSummary(
        thread_id=f"t-{subject[:8]}",
        subject=subject,
        senders=["sender@example.com"],
        profile_id="test",
        urgency=urgency,
        message_count=1,
        latest_at=datetime(2026, 8, 3, 6, 0, tzinfo=UTC),
    )


def _make_multi(sections: list[MorningBrief]) -> MultiBrief:
    return MultiBrief(
        brief_date=date(2026, 8, 3),
        generated_at=datetime(2026, 8, 3, 7, 0, tzinfo=UTC),
        lookback_hours=24,
        sections=sections,
    )


# ── MultiBrief model ──────────────────────────────────────────────────────────


def test_multi_brief_requires_timezone_aware_generated_at() -> None:
    with pytest.raises(ValueError):
        MultiBrief(
            brief_date=date(2026, 8, 3),
            generated_at=datetime(2026, 8, 3, 7, 0),  # naive — must fail
            lookback_hours=24,
        )


def test_multi_brief_sections_default_empty() -> None:
    m = MultiBrief(
        brief_date=date(2026, 8, 3),
        generated_at=datetime(2026, 8, 3, 7, 0, tzinfo=UTC),
        lookback_hours=24,
    )
    assert m.sections == []


# ── render_multi_brief ────────────────────────────────────────────────────────


def test_render_multi_brief_single_section_matches_render_brief() -> None:
    section = _make_section("alice@example.com", "Consulting", "consulting")
    multi = _make_multi([section])
    assert render_multi_brief(multi) == render_brief(section)


def test_render_multi_brief_no_sections_returns_no_accounts_message() -> None:
    multi = _make_multi([])
    output = render_multi_brief(multi)
    assert "# Morning Brief" in output
    assert "No accounts synced." in output


def test_render_multi_brief_two_sections_single_top_level_header() -> None:
    s1 = _make_section("alice@work.com", "Work Persona", "work")
    s2 = _make_section("alice@home.com", "Home Persona", "home")
    output = render_multi_brief(_make_multi([s1, s2]))
    assert output.count("# Morning Brief") == 1


def test_render_multi_brief_two_sections_both_account_emails_present() -> None:
    s1 = _make_section("alice@work.com", "Work Persona", "work")
    s2 = _make_section("alice@home.com", "Home Persona", "home")
    output = render_multi_brief(_make_multi([s1, s2]))
    assert "alice@work.com" in output
    assert "alice@home.com" in output


def test_render_multi_brief_two_sections_uses_h2_account_headers() -> None:
    s1 = _make_section("alice@work.com", "Work Persona", "work")
    s2 = _make_section("alice@home.com", "Home Persona", "home")
    output = render_multi_brief(_make_multi([s1, s2]))
    assert "## alice@work.com · Work Persona" in output
    assert "## alice@home.com · Home Persona" in output


def test_render_multi_brief_two_sections_uses_h3_band_headings() -> None:
    threads = [_make_thread("Big contract", UrgencyBand.CRITICAL)]
    s1 = _make_section("alice@work.com", "Work Persona", "work", threads=threads)
    s2 = _make_section("alice@home.com", "Home Persona", "home")
    output = render_multi_brief(_make_multi([s1, s2]))
    assert "### Critical" in output
    assert not re.search(r"^## Critical", output, re.MULTILINE)


def test_render_multi_brief_thread_content_from_both_accounts() -> None:
    s1 = _make_section(
        "alice@work.com",
        "Work Persona",
        "work",
        threads=[_make_thread("Invoice due today", UrgencyBand.HIGH)],
    )
    s2 = _make_section(
        "alice@home.com",
        "Home Persona",
        "home",
        threads=[_make_thread("Weekend plans", UrgencyBand.LOW)],
    )
    output = render_multi_brief(_make_multi([s1, s2]))
    assert "Invoice due today" in output
    assert "Weekend plans" in output


def test_render_multi_brief_sections_separated_by_divider() -> None:
    s1 = _make_section("alice@work.com", "Work", "work")
    s2 = _make_section("alice@home.com", "Home", "home")
    output = render_multi_brief(_make_multi([s1, s2]))
    assert "---" in output


# ── _token_cache_filename ─────────────────────────────────────────────────────


def test_token_cache_filename_no_alias_returns_default() -> None:
    assert _token_cache_filename(None) == TOKEN_CACHE_FILENAME


def test_token_cache_filename_with_alias_returns_scoped_name() -> None:
    assert _token_cache_filename("guided_ai_labs") == "graph_token_cache_guided_ai_labs.enc"


def test_token_cache_filename_each_alias_is_distinct() -> None:
    assert _token_cache_filename("acc_a") != _token_cache_filename("acc_b")


# ── run_multi_brief ───────────────────────────────────────────────────────────


CLEARED = (
    "ANTHROPIC_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
    "MICROSOFT_CLIENT_ID",
    "MICROSOFT_TENANT_ID",
    "MICROSOFT_CLIENT_SECRET",
    "MICROSOFT_REDIRECT_URI",
    "ENCRYPTION_KEY_BASE64",
    "INBOXMIND_HOME",
    "INBOXMIND_ACCOUNTS",
)


@pytest.fixture
def multi_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FieldEncryptor:
    for name in CLEARED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENCRYPTION_KEY_BASE64", Fernet.generate_key().decode())
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-key")
    home = tmp_path / "home"
    monkeypatch.setenv("INBOXMIND_HOME", str(home))
    return FieldEncryptor(os.environ["ENCRYPTION_KEY_BASE64"].encode())


def _seed_account(
    gateway: FakeTableGateway,
    *,
    email: str,
    subject: str,
    encryptor: FieldEncryptor,
) -> str:
    account_id = ensure_account(
        gateway,
        provider=Provider.MICROSOFT_GRAPH,
        primary_email=email,
        display_name=email.split("@")[0],
        org_type="organizational",
        scopes=["Mail.Read"],
    )
    now = datetime.now(tz=UTC)
    gateway.insert_rows(
        "emails",
        [
            {
                "account_id": account_id,
                "thread_id": f"t-{email[:6]}",
                "provider_message_id": f"m-{email[:6]}",
                "sender_email": "other@example.com",
                "subject": subject,
                "body_ciphertext": encryptor.encrypt_text("body text"),
                "body_hash": f"hash-{email[:6]}",
                "message_timestamp": (now - timedelta(hours=1)).isoformat(),
                "labels": ["INBOX"],
                "urgency": None,
                "classification": {},
            }
        ],
    )
    return account_id


def test_run_multi_brief_single_account_one_section(multi_env: FieldEncryptor) -> None:
    gateway = FakeTableGateway()
    acc_id = _seed_account(
        gateway, email="alice@example.com", subject="Quarterly update", encryptor=multi_env
    )
    personas = load_personas()
    link_account_persona(gateway, account_id=acc_id, persona=personas["consulting"])

    multi = run_multi_brief(gateway=gateway, encryptor=multi_env, personas=personas)

    assert len(multi.sections) == 1
    assert multi.sections[0].account_email == "alice@example.com"
    assert multi.sections[0].profile_id == "consulting"


def test_run_multi_brief_two_accounts_two_sections(multi_env: FieldEncryptor) -> None:
    gateway = FakeTableGateway()
    personas = load_personas()
    id1 = _seed_account(gateway, email="work@example.com", subject="Work mail", encryptor=multi_env)
    id2 = _seed_account(gateway, email="home@example.com", subject="Home mail", encryptor=multi_env)
    link_account_persona(gateway, account_id=id1, persona=personas["consulting"])
    link_account_persona(gateway, account_id=id2, persona=personas["guided_ai_labs"])

    multi = run_multi_brief(gateway=gateway, encryptor=multi_env, personas=personas)

    assert len(multi.sections) == 2
    emails = {s.account_email for s in multi.sections}
    assert emails == {"work@example.com", "home@example.com"}


def test_run_multi_brief_skips_account_without_persona(
    multi_env: FieldEncryptor, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeTableGateway()
    personas = load_personas()
    id1 = _seed_account(gateway, email="linked@example.com", subject="Linked", encryptor=multi_env)
    # id2 has no persona linked — should be skipped with a warning
    _seed_account(gateway, email="unlinked@example.com", subject="Unlinked", encryptor=multi_env)
    link_account_persona(gateway, account_id=id1, persona=personas["consulting"])

    multi = run_multi_brief(gateway=gateway, encryptor=multi_env, personas=personas)

    assert len(multi.sections) == 1
    assert multi.sections[0].account_email == "linked@example.com"
    out = capsys.readouterr().out
    assert "unlinked@example.com" in out
    assert "no persona linked" in out


def test_run_multi_brief_single_account_propagates_persona_error(
    multi_env: FieldEncryptor,
) -> None:
    gateway = FakeTableGateway()
    # Seed one account with no persona link → PersonaSelectionError must propagate
    _seed_account(gateway, email="solo@example.com", subject="Some email", encryptor=multi_env)
    personas = load_personas()

    with pytest.raises(PersonaSelectionError):
        run_multi_brief(gateway=gateway, encryptor=multi_env, personas=personas)


def test_run_multi_brief_no_accounts_raises_brief_data_error(
    multi_env: FieldEncryptor,
) -> None:
    gateway = FakeTableGateway()
    with pytest.raises(BriefDataError, match="inboxmind sync"):
        run_multi_brief(gateway=gateway, encryptor=multi_env, personas=load_personas())


def test_run_multi_brief_each_account_uses_own_persona(multi_env: FieldEncryptor) -> None:
    gateway = FakeTableGateway()
    personas = load_personas()
    id1 = _seed_account(gateway, email="a@example.com", subject="A mail", encryptor=multi_env)
    id2 = _seed_account(gateway, email="b@example.com", subject="B mail", encryptor=multi_env)
    link_account_persona(gateway, account_id=id1, persona=personas["consulting"])
    link_account_persona(gateway, account_id=id2, persona=personas["shaw"])

    multi = run_multi_brief(gateway=gateway, encryptor=multi_env, personas=personas)

    by_email = {s.account_email: s for s in multi.sections}
    assert by_email["a@example.com"].profile_id == "consulting"
    assert by_email["b@example.com"].profile_id == "shaw"


# ── CLI: connect --account / sync --account ───────────────────────────────────


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in CLEARED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENCRYPTION_KEY_BASE64", Fernet.generate_key().decode())
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "synthetic-client-id")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "common")
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-key")
    home = tmp_path / "home"
    monkeypatch.setenv("INBOXMIND_HOME", str(home))
    return home


def test_connect_without_account_uses_default_cache(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "n")
    exit_code = main(["connect"])
    assert exit_code == 1  # user said no, but the point is no alias-specific cache
    # No error about missing --account; connect ran and asked for consent
    default_cache = cli_env / TOKEN_CACHE_FILENAME
    assert not default_cache.exists()  # aborted before writing


def test_connect_with_account_alias_accepted_in_parser(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "n")
    # If --account parses correctly, we get exit 1 (user said no), not exit 2 (config error)
    exit_code = main(["connect", "--account", "guided_ai_labs"])
    assert exit_code == 1


def test_sync_with_account_alias_no_cache_returns_failure(
    cli_env: Path,
) -> None:
    # No cached token for "test_alias" → EXIT_FAILURE.
    # acquire_cached_token always calls client_factory (MSAL creates a new empty cache);
    # we give it a client that reports no accounts so the silent flow returns None → exit 1.
    from unittest.mock import MagicMock

    from tests.fakes import FakeTableGateway

    mock_client = MagicMock()
    mock_client.get_accounts.return_value = []

    exit_code = main(
        ["sync", "--account", "test_alias"],
        client_factory=lambda *_a, **_kw: mock_client,
        gateway_factory=lambda _s: FakeTableGateway(),
    )
    assert exit_code == 1
