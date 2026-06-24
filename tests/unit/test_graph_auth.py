from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError

from src.ingestion.graph_auth import (
    GRAPH_REQUIRED_SCOPES,
    MicrosoftGraphOAuthSettings,
    build_authorization_url,
)
from src.models.auth_models import OAuthConsentRecord
from src.models.email_models import Provider


def clear_graph_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET",
        "MICROSOFT_TENANT_ID",
        "MICROSOFT_REDIRECT_URI",
        "MICROSOFT_SCOPES",
    ):
        monkeypatch.delenv(key, raising=False)


def test_graph_oauth_settings_require_env_config(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_graph_env(monkeypatch)

    with pytest.raises(ValidationError):
        MicrosoftGraphOAuthSettings()


def test_graph_oauth_settings_build_authorization_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_graph_env(monkeypatch)
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "organizations")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "http://localhost:8765/auth/microsoft/callback",
    )

    settings = MicrosoftGraphOAuthSettings()
    url = build_authorization_url(settings, state="state-token")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == "/organizations/oauth2/v2.0/authorize"
    assert params["client_id"] == ["client-id"]
    assert params["response_type"] == ["code"]
    assert params["state"] == ["state-token"]
    assert params["scope"] == [" ".join(GRAPH_REQUIRED_SCOPES)]


def test_graph_oauth_settings_reject_write_capable_mail_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_graph_env(monkeypatch)
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "synthetic-test-value")
    monkeypatch.setenv(
        "MICROSOFT_REDIRECT_URI",
        "http://localhost:8765/auth/microsoft/callback",
    )

    with pytest.raises(ValidationError):
        MicrosoftGraphOAuthSettings(
            scopes=("offline_access", "User.Read", "Mail.Read", "Mail.Send"),
        )


def test_oauth_consent_requires_human_confirmation() -> None:
    with pytest.raises(ValidationError):
        OAuthConsentRecord(
            provider=Provider.MICROSOFT_GRAPH,
            account_id="acct-1",
            subject="user@example.com",
            scopes=list(GRAPH_REQUIRED_SCOPES),
            granted_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
            tenant_id="organizations",
            human_confirmed=False,
        )


def test_oauth_consent_requires_timezone_aware_grant_time() -> None:
    with pytest.raises(ValidationError):
        OAuthConsentRecord(
            provider=Provider.MICROSOFT_GRAPH,
            account_id="acct-1",
            subject="user@example.com",
            scopes=list(GRAPH_REQUIRED_SCOPES),
            granted_at=datetime(2026, 5, 15, 12, 0),
            tenant_id="organizations",
        )
