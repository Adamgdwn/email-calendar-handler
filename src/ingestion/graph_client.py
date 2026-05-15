from __future__ import annotations

from src.ingestion.graph_auth import GRAPH_REQUIRED_SCOPES
from src.models.email_models import AccountContext, RawEmail
from src.utils.rate_limiter import retry_provider_call


class MicrosoftGraphClient:
    """Microsoft Graph Outlook client placeholder for Milestone 1.2."""

    required_scopes = GRAPH_REQUIRED_SCOPES

    def fetch_delta(
        self,
        account_context: AccountContext,
        delta_link: str | None,
    ) -> list[RawEmail]:
        return retry_provider_call(lambda: self._fetch_delta_once(account_context, delta_link))

    def _fetch_delta_once(
        self,
        account_context: AccountContext,
        delta_link: str | None,
    ) -> list[RawEmail]:
        _ = account_context
        _ = delta_link
        return []
