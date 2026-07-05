from __future__ import annotations

from urllib.parse import urlencode

from pydantic import AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GRAPH_LOGIN_BASE_URL = "https://login.microsoftonline.com"
GRAPH_REQUIRED_SCOPES = ("offline_access", "User.Read", "Mail.Read", "Calendars.Read")
FORBIDDEN_GRAPH_SCOPE_FRAGMENTS = ("Mail.Send", "Mail.ReadWrite", ".Send", ".ReadWrite")


class MicrosoftGraphOAuthSettings(BaseSettings):
    """Public-client device-code flow is the primary auth path; client_secret and
    redirect_uri are only needed for the authorization-code fallback flow."""

    model_config = SettingsConfigDict(
        env_prefix="MICROSOFT_",
        env_file=".env",
        extra="ignore",
    )

    client_id: str = Field(min_length=1)
    client_secret: str | None = Field(default=None, min_length=1)
    tenant_id: str = Field(default="common", min_length=1)
    redirect_uri: AnyUrl | None = None
    scopes: tuple[str, ...] = GRAPH_REQUIRED_SCOPES

    @field_validator("client_secret", "redirect_uri", mode="before")
    @classmethod
    def blank_env_values_become_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("scopes")
    @classmethod
    def scopes_must_be_read_only(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        missing = set(GRAPH_REQUIRED_SCOPES) - set(value)
        if missing:
            msg = f"missing required Microsoft Graph scopes: {sorted(missing)}"
            raise ValueError(msg)

        forbidden = [
            scope
            for scope in value
            if any(fragment in scope for fragment in FORBIDDEN_GRAPH_SCOPE_FRAGMENTS)
        ]
        if forbidden:
            msg = f"forbidden write-capable Microsoft Graph scopes: {forbidden}"
            raise ValueError(msg)
        return value

    @property
    def authority(self) -> str:
        return f"{GRAPH_LOGIN_BASE_URL}/{self.tenant_id}"


def build_authorization_url(settings: MicrosoftGraphOAuthSettings, state: str) -> str:
    if settings.redirect_uri is None:
        msg = "authorization-code flow requires MICROSOFT_REDIRECT_URI; device-code flow does not"
        raise ValueError(msg)
    params = {
        "client_id": settings.client_id,
        "response_type": "code",
        "redirect_uri": str(settings.redirect_uri),
        "response_mode": "query",
        "scope": " ".join(settings.scopes),
        "state": state,
    }
    return f"{settings.authority}/oauth2/v2.0/authorize?{urlencode(params)}"
