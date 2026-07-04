# Ingestion Module Instructions

## WHAT
This directory owns provider adapters: OAuth boundaries, transports, payload
mapping, deduplication, thread assembly, delta/checkpoint sync, and (from
chunk 10) calendar reads.

## WHY
Providers change and multiply; the downstream pipeline must not. Everything
past this module consumes `RawEmail`, `EmailThread`, `CalendarEvent`, and
`AccountContext` only, so Gmail can land later without forking agents.

## HOW
- Normalize every provider payload into the models in `src.models` before it
  leaves this module.
- Enforce read-only scopes in settings validators; write scopes only ever
  arrive through the roadmap write-scope gate.
- Keep checkpoints provider-specific (`graph_delta_link`, `gmail_history_id`)
  inside `ProviderSyncCheckpoint`; agents never see them.
- Route provider HTTP through a `GraphTransport`-style protocol so tests use
  fakes; wrap real calls in `retry_provider_call`.
- Treat stale delta state as an explicit, typed resync path, not a silent
  retry.
- Use synthetic fixtures only; never commit real mailbox or calendar payloads.

## Do NOT
- Do not import agent classes here; ingestion feeds agents, never calls them.
- Do not persist plaintext bodies or tokens; encryption happens before any
  storage adapter sees content.
- Do not add write-capable provider scopes or mutate remote mailbox/calendar
  state.
- Do not let provider-specific fields leak into provider-neutral models.
