from __future__ import annotations

from src.models.email_models import AccountContext, RawEmail


class MicrosoftGraphClient:
    """Microsoft Graph client placeholder for Phase 2+."""

    def fetch_delta(
        self,
        account_context: AccountContext,
        delta_link: str | None,
    ) -> list[RawEmail]:
        _ = account_context
        _ = delta_link
        return []
