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
governance preflight passes. Configure the values in `.env`:

- `MICROSOFT_CLIENT_ID`
- `MICROSOFT_CLIENT_SECRET`
- `MICROSOFT_TENANT_ID`
- `MICROSOFT_REDIRECT_URI`

Use delegated read-only mail consent. Do not add `Mail.Send` or
`Mail.ReadWrite`.
