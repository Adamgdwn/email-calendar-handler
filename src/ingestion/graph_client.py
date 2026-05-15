from __future__ import annotations

from src.models.email_models import AccountContext, RawEmail


class MicrosoftGraphClient:
    """Microsoft Graph Outlook client placeholder for Milestone 1.2."""

    required_scopes = (
        "offline_access",
        "User.Read",
        "Mail.Read",
    )

    def fetch_delta(
        self,
        account_context: AccountContext,
        delta_link: str | None,
    ) -> list[RawEmail]:
        _ = account_context
        _ = delta_link
        return []
