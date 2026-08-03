"""IMAP credential storage and known-server registry.

Credentials are encrypted with the same Fernet key used for Graph token caches
so no new secrets are needed.  Only ISP / plain-password providers are listed
here; Gmail / Yahoo / iCloud require OAuth and are out of scope for this chunk.
"""

from __future__ import annotations

import imaplib
import ssl
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import BaseModel

# (domain → (host, port)) — extend as new ISP providers are verified.
IMAP_SERVERS: dict[str, tuple[str, int]] = {
    "shaw.ca": ("imap.shaw.ca", 993),
    "shawcable.net": ("imap.shaw.ca", 993),
    "rogers.com": ("imap.rogers.com", 993),
}


class ImapCredentials(BaseModel):
    host: str
    port: int
    username: str
    password: str


def imap_server_for_email(email: str) -> tuple[str, int] | None:
    """Return (host, port) for the email's domain, or None if not an IMAP provider."""
    domain = email.split("@", 1)[-1].lower()
    return IMAP_SERVERS.get(domain)


def _creds_path(alias: str, home: Path) -> Path:
    return home / f"imap_creds_{alias}.enc"


def is_imap_account(alias: str, home: Path) -> bool:
    """True when an encrypted IMAP credential file exists for this alias."""
    return _creds_path(alias, home).exists()


def save_imap_credentials(
    alias: str,
    creds: ImapCredentials,
    key_b64: str,
    home: Path,
) -> None:
    home.mkdir(parents=True, exist_ok=True)
    fernet = Fernet(key_b64.encode())
    ciphertext = fernet.encrypt(creds.model_dump_json().encode())
    _creds_path(alias, home).write_bytes(ciphertext)


def load_imap_credentials(alias: str, key_b64: str, home: Path) -> ImapCredentials:
    fernet = Fernet(key_b64.encode())
    plaintext = fernet.decrypt(_creds_path(alias, home).read_bytes())
    return ImapCredentials.model_validate_json(plaintext)


def test_imap_connection(creds: ImapCredentials) -> None:
    """Verify credentials; raises imaplib.IMAP4.error if login fails."""
    ctx = ssl.create_default_context()
    with imaplib.IMAP4_SSL(creds.host, creds.port, ssl_context=ctx) as imap:
        imap.login(creds.username, creds.password)
