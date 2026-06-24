# Changelog

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
