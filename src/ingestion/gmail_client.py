from __future__ import annotations

from src.models.email_models import AccountContext, RawEmail


class GmailClient:
    """Scope-limited Gmail client placeholder for Milestone 1.2."""

    required_scopes = (
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.labels",
    )

    def fetch_delta(
        self,
        account_context: AccountContext,
        history_id: str | None,
    ) -> list[RawEmail]:
        _ = account_context
        _ = history_id
        return []
