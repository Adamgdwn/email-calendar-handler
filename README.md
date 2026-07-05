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

Runnable today (2026-07-04): `inboxmind connect` (chunk 7) — device-code
sign-in, explicit y/N consent, Fernet-encrypted token cache —
`inboxmind sync` (chunk 8) — full-then-incremental Graph delta sync with
dedupe into ciphertext-only Supabase storage — and `inboxmind brief`
(chunk 9) — persona-keyword classification over synced mail rendered as the
first Morning Brief (`brief-YYYY-MM-DD.md`) — and, from chunk 10, `sync`
also pulls a read-only calendar window (`Calendars.Read`) so the brief
opens with today's agenda and boosts mail from today's attendees one
urgency band (display-only, reason recorded). See `docs/manual.md` for
app-registration, Supabase, and persona setup.

For context-cleared work sessions, use
[`docs/production-instructions.md`](docs/production-instructions.md) as the
single production handoff document. Example prompt: "carry on with chunk 11."

Next focus:
- chunk 11: `inboxmind review` — accept/modify/reject proposals feeding the learning loop
- chunk 12: local-only persona drafts

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
