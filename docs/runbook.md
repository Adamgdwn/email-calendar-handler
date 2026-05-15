# Runbook

## Governance Preflight

```bash
bash scripts/governance-preflight.sh
```

If this fails because `GOVERNANCE_HOME` is missing, do not connect real
credentials. The current exception covers scaffolding only.

## Validation

```bash
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
uv run python scripts/secret_scan.py
```

## Incident Posture

If any code path can modify external email state without `human_approved`, stop
work, remove or disable that path, and record the issue in the risk register.
