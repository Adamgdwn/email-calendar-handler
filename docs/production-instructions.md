# Production Instructions

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

## Universal Rules

- Run `bash scripts/governance-preflight.sh` before code or config changes.
- Work one chunk per session.
- Write or update tests before implementation when behavior changes.
- Keep Outlook/Microsoft Graph as the first provider.
- Keep provider-specific code behind ingestion adapters.
- Pass downstream state as Pydantic models only.
- Do not use real mailbox data in tests or fixtures.
- Do not add write-capable Microsoft Graph scopes.
- Do not send email, create drafts, or modify labels without `human_approved`.
- Run all validation before commit:

```bash
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
uv run python scripts/secret_scan.py
```

## Branch And PR Rules

- If PR #9 is still open, continue on `codex/outlook-first-ingestion-plan`.
- If PR #9 has merged, branch from updated `main`.
- Branch naming: `codex/chunk-N-short-description`.
- Commit format: `[module] feat/fix/docs: description`.
- Push every completed chunk and update the GitHub issue with validation notes.
- Do not merge protected `main` directly; use PR review.

## Chunk Map

### Chunk 0: Governance Preflight

Status: implemented in PR #9.

GitHub issue: #7

Goal: make local governance preflight pass without external `GOVERNANCE_HOME`.

Done criteria:
- `automation/governance_check.sh` exists
- `bash scripts/governance-preflight.sh` passes
- `project-control.yaml` reflects sensitive-data and agent controls
- no real credentials are connected before this passes

### Chunk 1: Outlook OAuth And Consent Boundary

Status: implemented in PR #9.

GitHub issue: #4

Goal: define the safe Microsoft Graph auth boundary before mailbox sync.

Done criteria:
- env-only Microsoft Graph settings
- allowed scopes: `offline_access`, `User.Read`, `Mail.Read`
- write-capable scopes rejected
- `OAuthConsentRecord` requires human confirmation
- Supabase has `account_consents`
- tests cover missing config, invalid scopes, and consent validation

### Chunk 2: Outlook RawEmail Mapping And Deduplication

Status: implemented in PR #9.

GitHub issue: #2

Goal: map Microsoft Graph message payloads into internal `RawEmail` records and
define deduplication before storage.

Read:
- `src/models/CLAUDE.md`
- `src/ingestion/graph_client.py`
- `src/models/email_models.py`

Expected files:
- `src/ingestion/graph_mapper.py`
- `src/models/email_models.py` if new provider metadata is needed
- `tests/unit/test_graph_mapper.py`
- `tests/fixtures/` with synthetic Outlook payloads only

Done criteria:
- Graph message `id` maps to `RawEmail.message_id`
- Graph `conversationId` maps to `RawEmail.thread_id`
- sender/recipients/subject/body/timestamp/labels map deterministically
- body hash helper is deterministic and account-scoped where needed
- duplicate provider message IDs are detectable before insert
- duplicate body hashes are detectable per account
- tests use synthetic data only

### Chunk 3: Provider-Neutral Thread Assembly

Status: implemented in PR #9.

GitHub issue: #3

Goal: assemble chronological `EmailThread` objects from `RawEmail` records.

Done criteria:
- grouped by `thread_id`
- messages sorted oldest to newest
- `participant_set`, `duration_days`, and `last_activity` computed
- works for Outlook now and Gmail later without downstream branching
- tests cover single-message and multi-message threads

### Chunk 4: Encrypted Storage And Rate Limiting

Status: implemented in PR #9.

GitHub issue: #5

Goal: persist typed email records safely and wrap provider calls with retry
behavior.

Done criteria:
- raw bodies are encrypted before storage
- plaintext body storage is not exposed by storage helpers
- Supabase adapter accepts typed records
- retry/backoff wraps Microsoft Graph calls
- tests cover encryption round trip and retry behavior

### Chunk 5: Microsoft Graph Delta Sync

Status: implemented in PR #9.

GitHub issue: #6

Goal: implement incremental Outlook sync using Microsoft Graph delta links.

Done criteria:
- first sync handles `@odata.nextLink` pagination until `@odata.deltaLink`
- subsequent sync starts from stored `deltaLink`
- stale/invalid delta state handling is explicit
- checkpoint fields distinguish Graph `deltaLink` from Gmail `historyId`
- tests cover first sync, next-page continuation, and subsequent sync

### Chunk 6: Multi-Provider/Profile Abstraction Check

Status: implemented in PR #9.

GitHub issue: #8

Goal: prove Outlook-first implementation is not hardcoded into downstream agent
behavior.

Done criteria:
- `AccountContext` is required on agent inputs
- provider adapters map to the same internal contracts
- downstream agents do not branch on provider unnecessarily
- docs explain how Gmail becomes the next provider

## Current Recommendation

After PR #9 is reviewed or merged, say:

```text
Carry on with chunk 7.
```

That starts the Outlook OAuth callback/token storage slice without connecting
real mailbox content.
