from __future__ import annotations

from src.models.email_models import AccountContext, EmailThread


class IngestAgent:
    """Placeholder ingestion boundary for Gmail and Microsoft Graph clients."""

    system_prompt_budget_tokens = 200

    def run(self, account_context: AccountContext) -> list[EmailThread]:
        _ = account_context
        return []
