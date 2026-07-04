# Risk Register

| Risk | Probability | Impact | Mitigation |
| --- | --- | --- | --- |
| Governance preflight unavailable locally | Medium | Medium | Accepted scaffolding-only exception; configure `GOVERNANCE_HOME` before credentials |
| Autonomous email action | Low | Critical | Require `human_approved`; no external write clients in Milestone 1.1 |
| Sensitive email leakage into tests | Medium | High | Synthetic fixtures only; secret scan in pre-commit and CI |
| Context accumulation harming agent quality | High | High | Typed stages, token budgets, retrieved context only |
| Persona bleed across accounts | Medium | High | AccountContext on agent inputs; persona YAML separated by profile |
| Council email is FOIP-visible public record | Medium | High | Encrypted storage; retention/deletion policy required before the write-scope gate; PIPEDA/FOIP review before Phase 4 |
| Personal vs organizational Microsoft account blocks auth flow | Medium | Medium | Device-code public client with `common` tenant first; documented auth-code fallback; record account type in consent log |
| LLM cost creep | Medium | Medium | Deterministic-first classification; per-agent token budgets; per-day budget guard; cost telemetry on every draft |
| Write scopes enabled before the system earns trust | Low | Critical | Explicit write-scope gate: >=70% filing acceptance over trailing 50 proposals, 14 days of daily use, governance review |
