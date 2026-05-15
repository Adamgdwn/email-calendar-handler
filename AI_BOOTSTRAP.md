# AI Bootstrap Rules

## Purpose
This repository must be workable by Claude, Codex, and local coding agents using
the same operating rules.

## Change Rules
- Scope each session to one milestone sub-item.
- Prefer typed models and small deterministic functions over prompt-heavy logic.
- Update docs when behavior, interfaces, governance, or architecture change.
- Explain any new dependency before adding it.

## Governance
- Run `bash scripts/governance-preflight.sh` before substantial changes.
- Review `project-control.yaml` for risk tier, exceptions, and controls.
- Record deviations as exceptions rather than ignoring them.

## Commands
- Install: `uv sync --all-groups`
- Lint: `uv run ruff check`
- Format: `uv run ruff format --check`
- Typecheck: `uv run mypy`
- Test: `uv run pytest`
- Secret scan: `uv run python scripts/secret_scan.py`

## Completion Standard
A task is not complete until relevant validation is run or a blocker is clearly
stated. Code that handles email data must keep human approval gates intact.
