# Production Instructions

Last Updated: 2026-07-04

Use this document as the single restart point after clearing the context window.
When the user says "carry on with chunk N", load this file first, then execute
only that chunk unless the user explicitly expands scope.

## Session Restart Prompt

Use this shape after a context clear:

```text
Carry on with chunk N from docs/production-instructions.md.
Run governance preflight, inspect the current branch/PR state, read the relevant
module CLAUDE.md, implement only that chunk, validate, commit, push, and update
GitHub issues/PR notes.
```

## Always Read First

1. `docs/production-instructions.md`
2. `CLAUDE.md`
3. `project-control.yaml`
4. The nearest module `CLAUDE.md` for the files being changed
5. The GitHub issue for the active chunk

## North Star

Every chunk serves the Morning Brief: one artifact each morning with the
calendar agenda, triaged new email by urgency and role, filing proposals, and
drafts awaiting review — all accept/reject-able, all feeding the learning loop.
The v1 surface is a CLI (`inboxmind connect|sync|brief|review|draft`) plus a
rendered brief file. See `docs/roadmap.md` for ship-gate metrics.

## Universal Rules

- Run `bash scripts/governance-preflight.sh` before code or config changes.
- Work one chunk per session.
- Write or update tests before implementation when behavior changes.
- Keep Outlook/Microsoft Graph as the first provider.
- Keep provider-specific code behind ingestion adapters.
- Pass downstream state as Pydantic models only.
- Do not use real mailbox data in tests or fixtures.
- Do not add write-capable Microsoft Graph scopes; read-only calendar scope
  (`Calendars.Read`) is allowed from chunk 10. The write-scope gate in
  `docs/roadmap.md` is the only path to `Mail.ReadWrite`.
- Do not send email, create drafts in the mailbox, or modify labels without
  `human_approved`.
- Run all validation before commit:

```bash
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
uv run python scripts/secret_scan.py
```

## Branch And PR Rules

- PR #9 merged on 2026-07-04; all new work branches from updated `main`.
- One small PR per chunk. Branch naming: `codex/chunk-N-short-description`.
- Commit format: `[module] feat/fix/docs: description`.
- Push every completed chunk and update the GitHub issue with validation notes.
- Do not merge protected `main` directly; use PR review.

## Chunk Map

### Chunks 0-6: Foundation (merged in PR #9)

Governance preflight fallback, Microsoft Graph OAuth boundary with read-only
scope enforcement, Outlook `RawEmail` mapping and dedupe keys, provider-neutral
thread assembly, encrypted email storage records with retry wrapper, Graph
delta sync with checkpointing, and provider/profile abstraction contracts.
Closed issues #1-#8.

### Chunk 7: Ignition — Real Graph Auth And `inboxmind connect`

Status: delivered 2026-07-04.

Goal: make the repository runnable for the first time — acquire a real
delegated token with read-only scopes and cache it encrypted.

Read:
- `src/ingestion/CLAUDE.md`
- `src/ingestion/graph_auth.py`
- `src/models/auth_models.py`

Expected files:
- `src/ingestion/graph_token_cache.py` (MSAL device-code flow + encrypted
  token cache using `FieldEncryptor`)
- `src/ingestion/graph_transport.py` (httpx-based `GraphTransport`)
- `src/cli.py` plus `[project.scripts] inboxmind = "src.cli:main"`
- `tests/unit/test_graph_token_cache.py`, `tests/unit/test_cli_connect.py`

Done criteria:
- MSAL device-code flow works with a public client app registration
  (`client_secret` becomes optional in settings; validators stay strict).
- Token cache is encrypted at rest with `ENCRYPTION_KEY_BASE64`; no plaintext
  tokens or refresh tokens ever touch disk.
- `inboxmind connect` runs the flow, requires an explicit y/N human
  confirmation, and writes a local `OAuthConsentRecord` log entry.
- A real `GraphTransport` implementation exists behind the existing protocol.
- New dependency (`httpx`) is exact-pinned and justified in the PR body.
- Tests cover flow success/failure, cache round trip, and header injection
  with fakes only.

Notes:
- Device code flow avoids hosting a redirect URI; keep the auth-code flow as a
  documented fallback if the tenant blocks public client flows.
- Personal vs organizational Microsoft accounts change app-registration
  behavior; record which account type was used in the consent log.

### Chunk 8: First Light — End-To-End Sync And `inboxmind sync`

Goal: real mailbox content flows through delta sync, dedupe, encryption, and
Supabase persistence.

Read:
- `src/memory/CLAUDE.md`
- `src/ingestion/graph_delta.py`
- `src/memory/email_store.py`
- `supabase/schema.sql`

Expected files:
- `src/memory/supabase_client.py` (typed client factory from env settings)
- `src/memory/checkpoint_store.py` (read/write `account_sync_checkpoints`)
- `src/cli.py` gains `sync`
- `tests/integration/test_sync_end_to_end.py` (fake transport fixtures through
  mapping, dedupe, encryption, and a fake table client)

Done criteria:
- `inboxmind sync` performs first full delta sync then incremental syncs from
  the stored `deltaLink`; stale delta state triggers an explicit resync path.
- Duplicate provider message IDs and account-scoped body hashes are skipped
  before insert.
- Bodies are ciphertext-only in storage; consent records upload to
  `account_consents`.
- Two consecutive real syncs succeed; the second is incremental.

### Chunk 9: Morning Brief v1 — `inboxmind brief`

Goal: the first daily-value artifact from real synced mail, deterministic
only.

Read:
- `src/agents/CLAUDE.md`
- `src/agents/classification_agent.py`
- `src/personas/*.yaml`

Expected files:
- `src/personas/loader.py` (typed persona/taxonomy loading)
- `src/agents/classification_agent.py` (wire persona `urgency_definitions`
  instead of hardcoded keyword lists)
- `src/brief/renderer.py` (terminal + `brief-YYYY-MM-DD.md` output)
- `src/cli.py` gains `brief`
- `tests/unit/test_persona_loader.py`, `tests/unit/test_brief_renderer.py`

Done criteria:
- Classification consumes metadata and a <=500-character excerpt only.
- Persona urgency keywords come from YAML; hardcoded lists are removed.
- Brief groups threads by urgency band, tags each with the account profile,
  and lists filing proposals with stable IDs for later review.
- Classifications persist to the `emails` table (`classification`, `urgency`,
  `sender_taxonomy`).
- A real morning run renders a brief from the user's synced mail.

### Chunk 10: Calendar Read — Agenda In The Brief

Goal: the calendar half of the product, read-only.

Read:
- `src/ingestion/CLAUDE.md`
- `src/ingestion/graph_auth.py`
- `src/models/email_models.py`

Expected files:
- `src/models/calendar_models.py` (provider-neutral `CalendarEvent`, tz-aware)
- `src/ingestion/graph_calendar.py` (Graph `calendarView` fetch + mapper)
- `src/brief/renderer.py` gains the agenda section
- `tests/unit/test_graph_calendar.py`, `tests/unit/test_calendar_models.py`

Done criteria:
- `Calendars.Read` joins the allowed scope set; `Calendars.ReadWrite` is
  rejected by tests.
- `CalendarEvent` carries start/end (timezone-aware), organizer, attendees,
  location, and online-meeting URL; event body text obeys the same excerpt
  discipline as email.
- `inboxmind sync` fetches today +/- configurable days of events.
- Meeting-aware urgency: mail from someone on today's attendee list is boosted
  one band (capped at critical), with the boost reason recorded.
- Brief shows the agenda before email triage.

### Chunk 11: Review And Learning — `inboxmind review`

Goal: close the feedback loop; the system starts earning rule promotions.

Read:
- `src/agents/CLAUDE.md`
- `src/agents/learning_agent.py`
- `src/models/feedback_models.py`

Expected files:
- `src/cli.py` gains `review` (interactive accept/modify/reject per proposal)
- `src/agents/learning_agent.py` (real promotion/demotion logic)
- `src/memory/rule_store.py` (LearningAgent-only write path to
  `filing_rules`)
- `tests/unit/test_learning_agent.py`, `tests/unit/test_cli_review.py`

Done criteria:
- Each review decision persists a `FeedbackRecord`.
- LearningAgent promotes a provisional rule to confirmed after 3 consecutive
  accepts of the same match criteria, demotes/retires on rejects, and remains
  the only writer of `filing_rules`.
- Confirmed rules still require `human_approved: true` before FilingAgent
  treats them as authoritative.
- Proposal acceptance rate is computed from the feedback table and shown in
  the brief footer (this metric drives the write-scope gate).

### Chunk 12: Drafts For Review — `inboxmind draft`

Goal: persona-toned reply drafts, strictly local output.

Read:
- `src/agents/CLAUDE.md`
- `src/agents/response_agent.py`
- `src/personas/*.yaml`

Expected files:
- `src/agents/response_agent.py` (Anthropic API behind a typed interface)
- `src/llm/anthropic_client.py` (thin, budget-guarded, injectable fake)
- `src/cli.py` gains `draft <thread-id>`
- `tests/unit/test_response_agent.py` (fake LLM client only)

Done criteria:
- ResponseAgent may receive full thread context (allowed for drafting) with
  persona tone and response constraints injected from YAML.
- Output goes to terminal/clipboard and the brief only; nothing is written to
  the mailbox and nothing is sent — `human_approved` remains false.
- Token budgets from agent class attributes are enforced via
  `src/utils/token_counter.py`; a cost line (tokens in/out) prints per draft.
- Draft edit distance is logged as a quality signal for later evaluation.

### Chunk 13 (Optional): LLM Classification Assist

Goal: spend tokens only where deterministic rules are weak.

Done criteria:
- Anthropic classification runs only when deterministic confidence is below a
  configured threshold, receives metadata plus the 500-character excerpt only,
  and returns a validated `Classification`.
- Results cache by account-scoped body hash; a per-day token budget guard
  stops overruns.
- Feedback outcomes compare deterministic vs LLM accuracy before any default
  flips.

### Write-Scope Gate (post-v1)

Not a chunk — a governance milestone. See `docs/roadmap.md`. Opening it
requires the acceptance-rate trigger, a governance preflight review, updated
risk register entries, and a scope-guard change that keeps per-action
`human_approved` enforcement.

## Current Recommendation

Say:

```text
Carry on with chunk 8.
```

That delivers first light: real mailbox content flowing through delta sync,
dedupe, and encryption into Supabase via `inboxmind sync`, using the
`GraphAuthenticator` and `HttpxGraphTransport` shipped in chunk 7.
