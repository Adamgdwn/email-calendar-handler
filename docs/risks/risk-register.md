# Risk Register

| Risk | Probability | Impact | Mitigation |
| --- | --- | --- | --- |
| Governance preflight unavailable locally | Medium | Medium | Accepted scaffolding-only exception; configure `GOVERNANCE_HOME` before credentials |
| Autonomous email action | Low | Critical | Require `human_approved`; no external write clients in Milestone 1.1 |
| Sensitive email leakage into tests | Medium | High | Synthetic fixtures only; secret scan in pre-commit and CI |
| Context accumulation harming agent quality | High | High | Typed stages, token budgets, retrieved context only |
| Persona bleed across accounts | Medium | High | AccountContext on agent inputs; persona YAML separated by profile |
