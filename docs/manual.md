# Manual

This milestone is developer-facing.

## Local Setup

1. Install `uv`.
2. Run `uv sync --all-groups`.
3. Copy `.env.example` to `.env` for local experiments.
4. Do not add real email credentials until governance preflight is configured.

## Human Approval

InboxMind must present filing and response actions for review. The current
scaffold has no external write capability. Future code must keep
`human_approved` checks close to every external action.

## Outlook Setup

Create a Microsoft Entra app registration for local development only after
governance preflight passes:

1. Supported account types: pick what matches the mailbox. "Accounts in any
   organizational directory and personal Microsoft accounts" covers both;
   set `MICROSOFT_TENANT_ID` to `common` (or `consumers` for a personal
   account, or your tenant ID for an organizational one).
2. InboxMind is a public client using the device-code flow: no client secret
   and no redirect URI. Under Authentication, set "Allow public client flows"
   to Yes.
3. API permissions: delegated `User.Read`, `Mail.Read`, and `Calendars.Read`
   only. Do not add `Mail.Send`, `Mail.ReadWrite`, or `Calendars.ReadWrite`.

Configure `.env`:

- `MICROSOFT_CLIENT_ID` (required)
- `MICROSOFT_TENANT_ID` (default `common`)
- `ENCRYPTION_KEY_BASE64` (Fernet key; the generate command is in
  `.env.example`)
- `INBOXMIND_HOME` (optional; default `~/.inboxmind`)
- `MICROSOFT_CLIENT_SECRET` and `MICROSOFT_REDIRECT_URI` only if the tenant
  blocks public client flows and you fall back to the authorization-code flow.

## Connect (Chunk 7)

```bash
uv run inboxmind connect
```

The command shows the read-only scopes, waits for an explicit `y`, then prints
a device code to enter at microsoft.com/devicelogin. On success it appends an
`OAuthConsentRecord` (including personal vs organizational account type) to
`$INBOXMIND_HOME/consent_log.jsonl`. Tokens are cached only as Fernet
ciphertext at `$INBOXMIND_HOME/graph_token_cache.enc`; re-running `connect`
reuses the cache silently instead of prompting again.

## Sync (Chunk 8)

One-time prerequisite: create a Supabase project, run `supabase/schema.sql`
in its SQL editor, and set in `.env`:

- `SUPABASE_URL` (the project URL)
- `SUPABASE_SERVICE_ROLE_KEY` (service role key; local server-side use only)

Then:

```bash
uv run inboxmind sync
```

Sync reuses the encrypted token cache (run `inboxmind connect` first — it
never starts a device flow itself), uploads any local consent records to
`account_consents` once, and pulls inbox changes through Microsoft Graph
delta sync. The first run is a full sync; later runs are incremental from the
delta link stored in `account_sync_checkpoints`, and stale delta state
triggers an automatic full resync. Email bodies land as Fernet ciphertext
only, and duplicate provider message IDs or account-scoped body hashes are
skipped before insert. The first sync also bootstraps the `personas` ->
`accounts` row chain with a `default` persona placeholder until
`inboxmind brief --profile` links a real YAML persona.

From chunk 10 each sync also fetches a read-only calendar window
(`--calendar-days N` widens it from the default today +/- 1 day) into the
`calendar_events` table after the mail checkpoint is saved, replacing the
whole window each run so cancelled or moved meetings never linger. Event
bodies are never stored.

Upgrading from 0.4.0: add the delegated `Calendars.Read` permission to the
app registration, run the `calendar_events` block from `supabase/schema.sql`
(table, index, row level security, policy) in the Supabase SQL editor once,
then re-run `uv run inboxmind connect` so the cached token gains the new
scope. Until then, `inboxmind sync` reports a calendar error naming exactly
that fix.

## Brief (Chunk 9)

```bash
uv run inboxmind brief --profile consulting
```

The first run needs `--profile` (one of `city_council`, `consulting`,
`habitat`, `prime_boilers`) to replace the placeholder persona from the first
sync; the choice is stored on the account, so later runs are just
`uv run inboxmind brief`. The command classifies mail from the last 24 hours
(`--hours` widens the window) using the persona's urgency keywords over
metadata and a 500-character excerpt of the locally decrypted body — full
bodies never reach agents. Classification, urgency, and sender taxonomy
persist to the `emails` table once per message; re-runs reclassify nothing.
The brief prints to the terminal and lands at
`$INBOXMIND_HOME/briefs/brief-YYYY-MM-DD.md`, with threads grouped by urgency
band, every filing proposal carrying a stable id for `inboxmind review`, and
(from chunk 11) a filing-feedback footer showing the proposal acceptance rate
and whether the write-scope gate is open.

From chunk 10 the brief opens with today's agenda (times in the account's
timezone, all-day events flagged, join links included) before email triage,
and mail from anyone on today's attendee list is boosted one urgency band
for display (capped at critical) with the reason shown on the thread line —
stored classifications are never rewritten.

## Review (Chunk 11)

```bash
uv run inboxmind review --profile consulting
```

Review walks the same filing proposals the brief showed (same lookback window;
`--hours` widens it), one at a time: `a`ccept, `m`odify (then type a new
slash-separated path), `r`eject, or `s`kip. Each decision is saved as one
`feedback` row — no mailbox state is ever touched. After the pass the
LearningAgent folds every recorded decision for the account into filing-rule
status: three consecutive accepts of the same path confirm a rule, a reject
retires it, and a modify (or any broken streak) leaves it provisional.
Confirmed rules still carry `human_approved = false`, so FilingAgent will not
treat them as authoritative until a human approves them, and LearningAgent
stays the only writer of `filing_rules`. The proposal acceptance rate shown in
the brief footer is the metric that governs the `Mail.ReadWrite` write-scope
gate (opens at 70%).
