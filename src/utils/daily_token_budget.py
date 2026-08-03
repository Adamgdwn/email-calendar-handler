"""Per-day token budget for LLM classification assist.

Persists usage in a JSON file under INBOXMIND_HOME so the budget survives
across CLI invocations within the same day and resets automatically at midnight.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class _BudgetRecord:
    date: str
    tokens_used: int


class DailyTokenBudget:
    def __init__(self, path: Path, daily_limit: int) -> None:
        self._path = path
        self._daily_limit = daily_limit

    def remaining(self) -> int:
        record = self._load()
        if record.date != date.today().isoformat():
            return self._daily_limit
        return max(0, self._daily_limit - record.tokens_used)

    def record(self, tokens: int) -> None:
        today = date.today().isoformat()
        existing = self._load()
        used = existing.tokens_used + tokens if existing.date == today else tokens
        self._path.write_text(json.dumps({"date": today, "tokens_used": used}))

    def tokens_used_today(self) -> int:
        record = self._load()
        if record.date != date.today().isoformat():
            return 0
        return record.tokens_used

    def _load(self) -> _BudgetRecord:
        if not self._path.exists():
            return _BudgetRecord(date="", tokens_used=0)
        try:
            raw = json.loads(self._path.read_text())
            return _BudgetRecord(
                date=str(raw.get("date", "")),
                tokens_used=int(raw.get("tokens_used", 0)),
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return _BudgetRecord(date="", tokens_used=0)
