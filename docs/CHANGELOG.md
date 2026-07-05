# Changelog

## 0.3.0 - 2026-07-04

- Chunk 8 (First Light): `inboxmind sync` pulls real mailbox content through
  Graph delta sync, dedupe, and encryption into Supabase.
- First sync is full; later syncs are incremental from the delta link stored
  in `account_sync_checkpoints`. Stale delta state clears the checkpoint and
  resyncs explicitly — `retry_provider_call` gained `retry_exception_types`
  so the stale-state signal is never burned as a transport retry.
- Sync bootstraps the `personas` -> `accounts` row chain (placeholder
  `default` persona until chunk 9), uploads local consent records to
  `account_consents` exactly once, and creates `threads` rows (forward-only
  `last_activity`) before inserting ciphertext-only email rows. Duplicate
  provider message IDs and account-scoped body hashes are skipped before
  insert.
- New `TableGateway` protocol in `src/memory/supabase_client.py` confines the
  postgrest fluent API to one module; all stores and tests depend on the
  protocol (in-memory fake, no network).
- `GraphAuthenticator.acquire_cached_token` adds a silent-only token path:
  sync never starts a device flow and directs to `inboxmind connect` instead.
- 21 new tests (92 total), including an end-to-end integration suite through
  fake transport and gateway. Zero new dependencies (`supabase` was already
  pinned).

## 0.2.0 - 2026-07-04

- Chunk 7 (Ignition): the repository is runnable for the first time through
  the `inboxmind` CLI (`[project.scripts]` entry point, hatchling packaging).
- `inboxmind connect` signs in with the MSAL device-code flow (public client:
  `client_secret` and `redirect_uri` are now optional and reserved for the
  authorization-code fallback), requires an explicit y/N human confirmation,
  and appends an `OAuthConsentRecord` — now carrying personal-vs-organizational
  account type — to a local consent log.
- The MSAL token cache persists only as Fernet ciphertext
  (`ENCRYPTION_KEY_BASE64`) with 0600 file permissions; access tokens stay
  `SecretStr`-wrapped in memory and never print.
- Added `HttpxGraphTransport`, the first real `GraphTransport`: Graph error
  payloads pass through for stale-delta detection, 429/5xx raise a typed
  retryable error, and `httpx==0.28.1` (already a transitive dependency) is
  exact-pinned.
- 32 new unit tests (71 total) cover cache round-trip encryption, device-flow
  success/failure, silent reuse, header injection, and CLI consent/config
  paths — fakes only, no network.

## 0.1.1 - 2026-07-04

- Merged PR #9 (Milestone 1.2 Outlook ingestion foundation, chunks 0-6) and
  moved to small per-chunk PRs from `main`.
- Refactored the plan around the Morning Brief north star: chunks 7-13 now
  each end in a usable CLI slice (`connect`, `sync`, `brief`, `review`,
  `draft`) with a defined v1 ship gate.
- Scoped calendar into v1 as read-only (`Calendars.Read`, chunk 10) with a
  provider-neutral `CalendarEvent` boundary and meeting-aware triage.
- Made the write-scope gate explicit: `Mail.ReadWrite` requires a >=70%
  filing-acceptance metric plus governance review; autonomy stays A1.
- Removed unused `langgraph` and `google-api-python-client` pins (never
  imported); each returns with justification when first needed.
- Added `src/ingestion/CLAUDE.md` module guidance and new risk register
  entries (FOIP records, account-type friction, LLM cost, premature write
  scopes).

## 0.1.0 - 2026-05-15

- Repurposed the repository into the InboxMind Milestone 1.1 Python scaffold.
- Added typed Pydantic contracts, agent stubs, taxonomy/persona config, Supabase
  schema, validation tooling, CI, and governance exception tracking.
- Pivoted Milestone 1.2 planning to Outlook/Microsoft Graph first, with Gmail as
  the second provider after the provider-neutral pipeline is proven.
- Restored local governance preflight and added the Microsoft Graph OAuth
  configuration plus consent logging boundary for Outlook-first ingestion.
- Added a single production instruction document for context-cleared sessions
  and numbered chunk handoffs.
- Added Microsoft Graph message mapping into `RawEmail`, account-scoped body
  dedupe keys, duplicate detection helpers, and synthetic Outlook fixtures.
- Added provider-neutral `RawEmail` to `EmailThread` assembly with chronological
  ordering, participant normalization, duration, and last-activity calculation.
- Added encrypted email storage records, a typed Supabase insert adapter, and a
  provider retry wrapper for Microsoft Graph calls.
- Added Microsoft Graph message delta sync pagination, stored delta checkpoint
  modeling, deleted-message tracking, and stale delta state handling.
- Added provider-neutral sync contracts and tests that protect the downstream
  agent boundary from Outlook/Gmail branching.
