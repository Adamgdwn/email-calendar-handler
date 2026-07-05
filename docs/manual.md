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
