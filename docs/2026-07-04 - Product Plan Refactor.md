# 2026-07-04 - Product Plan Refactor

Decision record for the product-direction pass on InboxMind. The canonical
plan artifacts are `docs/roadmap.md`, `docs/production-instructions.md`, and
`docs/architecture.md`; this document records why they changed.

## Intent Restated

InboxMind is a chief-of-staff for a four-role professional (City Council,
consulting, Habitat for Humanity, Prime Boilers): triage across roles, file
consistently per role taxonomy, draft in each role's voice, learn from
corrections, never act without human approval.

## Assessment (state on 2026-07-04)

Chunks 0-6 built a disciplined, well-tested ingestion engine (delta sync,
mapping, dedupe, thread assembly, encryption, retry, provider-neutral
contracts) — but:

1. No path to "usable": no entrypoint, CLI, or runner existed anywhere; no
   chunk ended with something the user runs.
2. Calendar was in the project name and absent from every plan document.
3. The read-only scope guard contradicted the roadmap's own filing/drafting
   endgame, with no defined gate to ever lift it.
4. The learning loop had no metric defining when a rule earns promotion or
   when write scopes are justified.
5. Process debt: the entire milestone sat in one seven-week-old PR, and
   unused pinned dependencies (langgraph, google-api-python-client) generated
   dependabot noise and supply-chain surface with zero imports.

## Decisions

All three confirmed by Adam on 2026-07-04:

1. Calendar is in v1, read-only (`Calendars.Read`), as chunk 10: agenda in
   the brief plus meeting-aware urgency.
2. v1 surface is a CLI plus rendered brief file
   (`inboxmind connect|sync|brief|review|draft`); web UI stays Phase 4.
3. PR #9 merged 2026-07-04; small per-chunk PRs from `main` from now on.

Director calls made without a blocking question (reversible, conventional):

- North star framing: the Morning Brief; every slice ends in a usable
  artifact.
- Explicit write-scope gate (>=70% filing acceptance over trailing 50
  proposals, 14 days daily use, governance review) instead of an implicit
  forever-ban that the roadmap would eventually have to violate.
- Dropped unused `langgraph` and `google-api-python-client` pins; each
  returns with justification when first imported (consistent with the
  existing "typed stubs until graph wiring is justified" decision).
- Added `src/ingestion/CLAUDE.md` (the busiest module had no local guidance).
- New risks registered: FOIP-visible council records, personal-vs-org
  Microsoft account friction, LLM cost creep, premature write scopes.

## Resulting Chunk Map

See `docs/production-instructions.md`: chunk 7 (ignition/auth), 8 (end-to-end
sync), 9 (Morning Brief v1), 10 (calendar read), 11 (review + learning),
12 (drafts for review), 13 (optional LLM classification assist), then the
write-scope gate as a governance milestone, then Phase 2 (Gmail).
