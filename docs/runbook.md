# Runbook

## Governance Preflight

```bash
bash scripts/governance-preflight.sh
```

The repository includes a local fallback check in
`automation/governance_check.sh`. If preflight fails, do not connect real
credentials.

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

## Outlook Credentials

Before setting Microsoft Graph credentials:

1. Run governance preflight.
2. Confirm scopes are read-only: `offline_access`, `User.Read`, `Mail.Read`.
3. Confirm consent logging writes an `OAuthConsentRecord`.
4. Use synthetic fixtures until the encrypted storage adapter is tested.
