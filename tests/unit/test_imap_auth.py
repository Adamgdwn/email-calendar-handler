"""Tests for IMAP credential storage and provider lookup."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.ingestion.imap_auth import (
    IMAP_SERVERS,
    ImapCredentials,
    imap_server_for_email,
    is_imap_account,
    load_imap_credentials,
    save_imap_credentials,
)


@pytest.fixture
def key_b64() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "inboxmind"


@pytest.fixture
def creds() -> ImapCredentials:
    return ImapCredentials(
        host="imap.shaw.ca",
        port=993,
        username="user@shaw.ca",
        password="synthetic-test-pw",  # noqa: S106
    )


# ── server lookup ─────────────────────────────────────────────────────────────


def test_known_domain_returns_server() -> None:
    for domain in IMAP_SERVERS:
        result = imap_server_for_email(f"user@{domain}")
        assert result is not None
        assert isinstance(result[0], str)
        assert isinstance(result[1], int)


def test_unknown_domain_returns_none() -> None:
    assert imap_server_for_email("user@outlook.com") is None
    assert imap_server_for_email("user@guidedailabs.com") is None


def test_domain_lookup_is_case_insensitive() -> None:
    assert imap_server_for_email("user@SHAW.CA") == imap_server_for_email("user@shaw.ca")


# ── credential round-trip ─────────────────────────────────────────────────────


def test_save_and_load_roundtrip(key_b64: str, home: Path, creds: ImapCredentials) -> None:
    save_imap_credentials("shaw", creds, key_b64, home)
    loaded = load_imap_credentials("shaw", key_b64, home)
    assert loaded == creds


def test_password_is_not_stored_plaintext(key_b64: str, home: Path, creds: ImapCredentials) -> None:
    save_imap_credentials("shaw", creds, key_b64, home)
    raw = (home / "imap_creds_shaw.enc").read_bytes()
    assert b"synthetic-test-pw" not in raw


def test_different_aliases_produce_different_files(
    key_b64: str, home: Path, creds: ImapCredentials
) -> None:
    save_imap_credentials("shaw", creds, key_b64, home)
    save_imap_credentials("rogers", creds, key_b64, home)
    assert (home / "imap_creds_shaw.enc").exists()
    assert (home / "imap_creds_rogers.enc").exists()


def test_wrong_key_raises_on_load(home: Path, creds: ImapCredentials) -> None:
    key_a = Fernet.generate_key().decode()
    key_b = Fernet.generate_key().decode()
    save_imap_credentials("shaw", creds, key_a, home)
    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        load_imap_credentials("shaw", key_b, home)


# ── is_imap_account ───────────────────────────────────────────────────────────


def test_is_imap_account_true_after_save(key_b64: str, home: Path, creds: ImapCredentials) -> None:
    save_imap_credentials("shaw", creds, key_b64, home)
    assert is_imap_account("shaw", home) is True


def test_is_imap_account_false_when_missing(home: Path) -> None:
    assert is_imap_account("shaw", home) is False


def test_is_imap_account_false_for_graph_alias(tmp_path: Path) -> None:
    # Graph accounts have a token cache but no imap_creds file.
    home = tmp_path / "inboxmind"
    home.mkdir()
    (home / "graph_token_cache_guidedailabs.enc").write_bytes(b"fake")
    assert is_imap_account("guidedailabs", home) is False
