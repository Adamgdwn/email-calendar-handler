# InboxMind

InboxMind is a Python email intelligence project for a phased, human-approved
MVP. The first provider implementation targets Microsoft Outlook through
Microsoft Graph, then expands to multiple providers and profiles after the first
loop is proven.

The repository folder name remains `email and calendar handler` for now. The
internal package and project codename are `inboxmind`.

## Current Milestone

Milestone 1.2: Outlook/Microsoft Graph ingestion layer.

Included now:
- Python 3.12 monorepo layout
- Root and per-module `CLAUDE.md` files
- Pydantic contracts for email, filing, feedback, and personas
- Supervisor + specialist agent stubs
- Filing taxonomy and persona YAML seeds
- Supabase schema foundation with RLS enabled
- Exact-pinned dependencies, pre-commit, CI, tests, and secret scanning

Next focus:
- Microsoft Graph OAuth and consent logging
- Outlook message mapping into typed `RawEmail` records
- per-folder Graph delta sync checkpointing
- provider-neutral thread assembly and deduplication
- encrypted storage boundaries before real mailbox content is persisted

## Commands

```bash
uv sync --all-groups
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
uv run python scripts/secret_scan.py
```

## Governance

Run this before substantial changes:

```bash
bash scripts/governance-preflight.sh
```

Current accepted exception: local preflight requires `GOVERNANCE_HOME`. Configure
governance before real Outlook credentials or mailbox content are connected.

## Safety Rules

- No autonomous email sending, draft creation, or label modification.
- External email actions require a stored `human_approved: true` flag.
- Classification receives sender, subject, labels, and a 500-character excerpt,
  never the full body.
- Agent state passes through Pydantic models, not raw dicts or JSON strings.
- `filing_rules` writes belong to LearningAgent-controlled flows only.
