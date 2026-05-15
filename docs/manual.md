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
