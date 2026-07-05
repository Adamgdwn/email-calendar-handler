# START HERE — InboxMind

Last Updated: 2026-07-05

Fast orientation + turnover. Deeper detail: `docs/production-instructions.md`
(chunk map), `docs/roadmap.md`, `docs/manual.md`.

## What it is
Python 3.12 email + calendar intelligence MVP. First provider: Outlook /
Microsoft Graph (read-only). Deterministic, typed, human-approved. North star =
the **Morning Brief**: one daily artifact (agenda, triaged mail, filing
proposals, draft replies), every item accept/reject-able, feeding a learning loop.

## Status (v0.6.0)
- Chunks 0–11 shipped to `main` (trunk-based: commit+push each chunk, no PRs).
  183 tests green; `ruff`/`mypy`/secret-scan clean.
- CLI surface: `inboxmind connect | sync | brief | review` (+ `draft` = next).

## Done today (2026-07-05) — real-run env + launcher
- **`.env` wired** (gitignored): Supabase project `bmwrgspguatpduvoiexs`
  (schema applied, service_role verified live) + reused M365 app
  `9aeeeae6-…` / **adamgoodwin@guidedailabs.com** + fresh Fernet key.
- **Desktop launcher**: `~/Desktop/InboxMind.desktop` + app-menu entry + custom
  "intelligent inbox" icon. Reproducible via `bash scripts/install-launcher.sh`.
  Menu wrapper `scripts/inboxmind-app.sh`.
- Test-isolation fix (`tests/conftest.py`) so a real `.env` doesn't break tests.

## Blocked on Adam (the only manual step)
Run **`inboxmind connect`** once (device-code sign-in as
adamgoodwin@guidedailabs.com + y/N consent → encrypted token cache). Then
`sync` → `brief` → `review` run on real mail. Gotcha: an ambient master-env
`SUPABASE_*` overrides `.env`; the launcher auto-unsets it.

## Next build
**Chunk 12 — `inboxmind draft`**: persona-toned reply drafts, local output only,
`human_approved` stays false. This is where per-account tone lands (Guided AI
Labs leadership / Red Deer professional / Shaw relaxed). Resume with:
`Carry on with chunk 12.`

## Parked vision — the "frame"
The terminal menu is a stopgap and feels clunky. Target form factor: a **polished,
web-like daily-briefing UI** (sophisticated newsfeed style), not a terminal.
Multi-account (read all inboxes, tone per account) is the planned expansion.
