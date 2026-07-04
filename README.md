# InboxMind

InboxMind is a Python email and calendar intelligence project for a phased,
human-approved MVP. The first provider implementation targets Microsoft
Outlook through Microsoft Graph, then expands to multiple providers and
profiles after the first loop is proven.

The repository folder name remains `email and calendar handler` for now. The
internal package and project codename are `inboxmind`.

## North Star

The Morning Brief: one artifact each morning with today's calendar agenda,
new email triaged by urgency and role, filing proposals, and drafts awaiting
review — every item accept/reject-able, every response feeding the learning
loop.

## Current Milestone

Milestone 1.3: Ignition and Morning Brief v1 (chunks 7-13).

Merged foundation (PR #9, chunks 0-6): governance preflight, read-only Graph
OAuth boundary, Outlook message mapping and dedupe, provider-neutral thread
assembly, encrypted storage records, delta sync checkpointing, and
provider/profile abstraction contracts.

The v1 surface is a CLI plus a rendered brief file:

```text
inboxmind connect   # device-code OAuth, human-confirmed consent, encrypted token cache
inboxmind sync      # incremental mail + calendar sync into encrypted storage
inboxmind brief     # the Morning Brief (terminal + brief-YYYY-MM-DD.md)
inboxmind review    # accept/modify/reject proposals; feeds the learning loop
inboxmind draft     # persona-toned reply drafts, terminal/clipboard only
```

For context-cleared work sessions, use
[`docs/production-instructions.md`](docs/production-instructions.md) as the
single production handoff document. Example prompt: "carry on with chunk 7."

Next focus:
- chunk 7: MSAL device-code auth, encrypted token cache, real Graph transport
- chunk 8: end-to-end incremental sync into encrypted Supabase storage
- chunk 9: deterministic Morning Brief with persona keyword wiring
- chunk 10: read-only calendar (`Calendars.Read`) agenda and meeting-aware triage
- chunks 11-12: review/learning loop, then local-only drafts

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

The repository includes a local governance fallback check. Preflight must pass
before real Outlook credentials or mailbox content are connected.

## Safety Rules

- No autonomous email sending, draft creation, or label modification.
- External email actions require a stored `human_approved: true` flag.
- Mail and calendar scopes are read-only; `Mail.ReadWrite` is reachable only
  through the write-scope gate defined in [`docs/roadmap.md`](docs/roadmap.md).
- Classification receives sender, subject, labels, and a 500-character excerpt,
  never the full body. Calendar event bodies obey the same excerpt limit.
- Agent state passes through Pydantic models, not raw dicts or JSON strings.
- `filing_rules` writes belong to LearningAgent-controlled flows only.
