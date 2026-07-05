# Changelog

## 0.6.0 - 2026-07-05

- Chunk 11 (Review and Learning): `inboxmind review` walks the brief's filing
  proposals one at a time (accept / modify / reject / skip) and records every
  decision as a `feedback` row. No mailbox state is touched.
- LearningAgent gained real, deterministic promotion logic keyed on the filing
  path: three consecutive accepts confirm a rule, a reject retires it, and a
  modify or any broken streak leaves or returns it to provisional. It never
  sets `human_approved`, so a confirmed rule still needs explicit human
  approval before FilingAgent trusts it.
- `SupabaseRuleStore.save_rules` is now the single sanctioned `filing_rules`
  writer (rows stamped `created_by = 'learning_agent'`), invoked only by the
  review flow after `LearningAgent.run`; promotions update existing rows in
  place so approval state survives.
- New `feedback_store` persists and reads `feedback`, and computes the proposal
  acceptance rate that the Morning Brief now shows in a filing-feedback footer
  alongside the write-scope gate (opens at 70%).
- Brief and review share one `build_proposal_context`, so a reviewed proposal
  is exactly the one the brief displayed (same stable ids).
- Development moved to trunk-based: chunks now land straight on `main` (no
  per-chunk PR). Chunk 10 (PR #21) was the last PR-merged chunk.
- 28 new tests (183 total). Zero new dependencies.

## 0.5.0 - 2026-07-04

- Chunk 10 (Calendar Read): `inboxmind sync` now also fetches a read-only
  Microsoft Graph `calendarView` window (`Calendars.Read`; today +/- 1 day,
  `--calendar-days N` to widen) after the mail checkpoint is saved, and the
  Morning Brief opens with today's agenda before email triage.
- Provider-neutral `CalendarEvent`/`EventAttendee` models: timezone-aware
  start/end, organizer, deduped lowercased attendees, location,
  online-meeting URL, and a 500-character body excerpt matching the email
  discipline — event bodies are never persisted at all.
- New `calendar_events` table (index, RLS, service-role policy) with
  replace-window semantics: each sync deletes the fetched window plus any
  rows for refetched event ids, then inserts fresh, so cancelled and moved
  meetings never linger; duplicate provider ids collapse last-wins.
- Meeting-aware triage: mail from anyone on today's attendee list is boosted
  one urgency band for display (capped at critical) with the reason recorded
  on the thread line; stored classifications are never rewritten. Today is
  the account-timezone day, and events qualify by overlap so cross-midnight
  and foreign-timezone all-day meetings still surface.
- `Calendars.Read` joined the enforced scope set (`Calendars.ReadWrite`
  stays rejected by the `.ReadWrite` fragment guard, now covered by tests);
  `TableGateway` gained `lt` filtering and `delete_rows`.
- 36 new tests (155 total). Zero new dependencies.

## 0.4.0 - 2026-07-04

- Chunk 9 (Morning Brief v1): `inboxmind brief` renders the first daily-value
  artifact from synced mail — terminal output plus
  `$INBOXMIND_HOME/briefs/brief-YYYY-MM-DD.md`.
- Persona urgency keywords now come from YAML: `src/personas/loader.py` loads
  the four repo personas into typed `PersonaProfile` models
  (`urgency_definitions` is now `dict[UrgencyBand, list[str]]`, keys validated,
  keywords lowercased), and `ClassificationAgent` takes the persona at
  construction — the hardcoded keyword lists are gone. No keyword match lands
  `low` with baseline confidence, so persona `normal` terms are meaningful.
- Classification consumes metadata plus a 500-character excerpt of the locally
  decrypted body only, and persists `classification`, `urgency`, and
  `sender_taxonomy` to the `emails` table exactly once per message (re-runs
  reclassify nothing).
- The brief groups threads by urgency band, tags each with the account
  profile, and lists filing proposals with stable sha256-derived ids for
  chunk 11's review loop; rules are read through the new `SupabaseRuleStore`
  (`filing_rules` writes stay LearningAgent-only).
- `--profile` upgrades the chunk-8 placeholder persona: the YAML persona row
  is upserted and linked to the account once, then later runs need no flag.
- `TableGateway.select_rows` gained a `gte` filter for the lookback window.
- 27 new tests (119 total), including sync-then-brief integration coverage.
  Zero new dependencies (`pyyaml` was already pinned).

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
