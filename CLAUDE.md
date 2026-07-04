# InboxMind Claude Instructions

## WHAT
InboxMind is a Python 3.12 email intelligence pipeline for a phased MVP:
ingest one Outlook/Microsoft Graph account first, classify email metadata,
propose filing, learn from human feedback, and draft replies only for review.

## WHY
The project handles sensitive communications. Production behavior must be typed,
auditable, low-autonomy, and cheap to run. Deterministic Python wins over LLM
reasoning whenever rules are enough.

## HOW
- Run `bash scripts/governance-preflight.sh` and review `project-control.yaml`
  before substantial changes.
- For resumed work after a context clear, start with
  `docs/production-instructions.md`.
- Use `uv sync --all-groups` for setup.
- Validate with `uv run ruff check`, `uv run ruff format --check`,
  `uv run mypy`, `uv run pytest`, and `uv run python scripts/secret_scan.py`.
- Keep dependencies exact-pinned in `pyproject.toml`.
- Pass state between agents as Pydantic models only.
- Keep module-specific guidance in local `CLAUDE.md` files.
- Update controlled docs when architecture, commands, or behavior changes.

## Do NOT
- Do not send email, create drafts, or modify labels without `human_approved`.
- Do not pass full email bodies into classification, filing, or relationship agents.
- Do not write raw dict or JSON-string state between agents.
- Do not hardcode credentials or sample real email content.
- Do not let any direct writer modify `filing_rules` except LearningAgent.
- Do not grow a single agent into a monolith; split `run()` over 80 lines.
