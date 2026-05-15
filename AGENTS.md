# Agent Instructions

Before making substantial code or configuration changes in this repository:

1. run the governance preflight check
2. review `project-control.yaml`
3. note any open exceptions relevant to the work
4. proceed only after the project passes preflight or any gaps are explicitly accepted

## Preflight

```bash
bash scripts/governance-preflight.sh
```

## Working Rules

- Follow the repository standards by default.
- Do not silently skip required documentation or controls.
- Record justified deviations as exceptions.
- Reassess governance when risk, autonomy, data sensitivity, or money movement changes.

