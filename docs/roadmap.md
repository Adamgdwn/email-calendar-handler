# Roadmap

Last Updated: 2026-07-04

## North Star

The Morning Brief: one artifact each morning showing today's calendar agenda,
new email triaged by urgency and role, filing proposals, and drafts awaiting
review. Every item is accept/reject-able, and every response feeds the
learning loop. Each roadmap slice must end with something the user runs that
week; infrastructure exists only in service of that artifact.

## Phase 1: Single-Account Usable v1 (Outlook)

Foundation chunks 0-6 (scaffolding, OAuth boundary, mapping, thread assembly,
encrypted storage, delta sync, provider-neutral contracts) merged in PR #9.

Remaining slices, in order (details in
[`production-instructions.md`](production-instructions.md)):

1. Chunk 7 — Ignition: MSAL device-code auth, encrypted token cache, real
   Graph transport, `inboxmind connect`.
2. Chunk 8 — First light: end-to-end incremental sync into encrypted Supabase
   storage, `inboxmind sync`.
3. Chunk 9 — Morning Brief v1: deterministic classification with persona
   keyword wiring, filing proposals, `inboxmind brief`.
4. Chunk 10 — Calendar read: `Calendars.Read` scope, provider-neutral
   `CalendarEvent`, agenda in the brief, meeting-aware urgency.
5. Chunk 11 — Review and learning: `inboxmind review` feedback loop,
   LearningAgent rule promotion, acceptance-rate metric.
6. Chunk 12 — Drafts for review: persona-toned Anthropic drafts to
   terminal/clipboard only, `inboxmind draft`.
7. Chunk 13 (optional) — LLM classification assist where deterministic
   confidence is low, budget-guarded.

### v1 Ship Gate (Definition of Usable)

- `connect`, `sync`, `brief`, `review`, and `draft` all work against the real
  Outlook account.
- `sync && brief` completes in under 2 minutes with no unhandled errors for 14
  consecutive days.
- At least one filing rule promoted to confirmed through real review feedback.
- The user checks the brief before opening Outlook (subjective but binding).

## Write-Scope Gate (post-v1, explicit governance milestone)

The current Graph scope guard forbids all write-capable scopes. Filing moves
and mailbox draft creation require `Mail.ReadWrite`, so this gate must be
consciously opened, never drifted into:

- Trigger: filing-proposal acceptance >= 70% over the trailing 50 proposals,
  plus >= 14 days of daily use, plus a governance preflight review.
- Then: add `Mail.ReadWrite` (delegated), enforce per-action `human_approved`,
  enable approved-only filing moves and drafts saved to the mailbox.
- Autonomy level stays A1: every external write is individually
  human-approved.

## Phase 2: Second Account and Second Provider

Gmail becomes the next provider after Outlook is proven. Account isolation,
municipal taxonomy, and no persona bleed across accounts are required before
broader use. Calendar write (scheduling proposals) is considered here at the
earliest, behind the same human-approval gate.

## Phase 3: Relationship Enrichment

Influence propagation, role disambiguation, and relationship context in draft
suggestions.

## Phase 4: Multi-Account UI

All target accounts, web UI, onboarding, and PIPEDA/FOIP compliance review.
