"""Shared pytest fixtures.

Isolate the suite from a developer's real project ``.env``. Every settings
class reads ``env_file=".env"`` relative to the working directory, so tests
that assert missing/invalid-config behaviour would otherwise silently pick up
the real ``.env`` and fail. Tests provide configuration through
``monkeypatch.setenv`` only, so disabling the dotenv source keeps them
hermetic without changing runtime behaviour (this fixture never runs in
production).
"""

from __future__ import annotations

import pytest

from src.cli import AppSettings
from src.ingestion.graph_auth import MicrosoftGraphOAuthSettings
from src.memory.supabase_client import SupabaseSettings

_SETTINGS_CLASSES = (AppSettings, MicrosoftGraphOAuthSettings, SupabaseSettings)


@pytest.fixture(autouse=True)
def _isolate_project_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop settings classes from reading the repo-root ``.env`` during tests."""
    for settings_cls in _SETTINGS_CLASSES:
        config = dict(settings_cls.model_config)
        config["env_file"] = None
        monkeypatch.setattr(settings_cls, "model_config", config)
