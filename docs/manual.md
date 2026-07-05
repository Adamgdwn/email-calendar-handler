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
3. API permissions: delegated `User.Read` and `Mail.Read` only. Do not add
   `Mail.Send` or `Mail.ReadWrite`.

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
band and every filing proposal review-only (stable ids) until
`inboxmind review` arrives in chunk 11.
