from __future__ import annotations

from urllib.parse import urlencode

from pydantic import AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GRAPH_LOGIN_BASE_URL = "https://login.microsoftonline.com"
GRAPH_REQUIRED_SCOPES = ("offline_access", "User.Read", "Mail.Read")
FORBIDDEN_GRAPH_SCOPE_FRAGMENTS = ("Mail.Send", "Mail.ReadWrite", ".Send", ".ReadWrite")


class MicrosoftGraphOAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MICROSOFT_",
        env_file=".env",
        extra="ignore",
    )

    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    tenant_id: str = Field(default="common", min_length=1)
    redirect_uri: AnyUrl
    scopes: tuple[str, ...] = GRAPH_REQUIRED_SCOPES

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
    params = {
        "client_id": settings.client_id,
        "response_type": "code",
        "redirect_uri": str(settings.redirect_uri),
        "response_mode": "query",
        "scope": " ".join(settings.scopes),
        "state": state,
    }
    return f"{settings.authority}/oauth2/v2.0/authorize?{urlencode(params)}"
