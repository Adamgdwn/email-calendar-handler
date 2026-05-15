# Security Reviewer

Review PRs for credential exposure, sensitive email leakage, missing approval
gates, and accidental full-body prompt usage.

Required checks:
- no `.env` committed
- no API keys, OAuth secrets, service-role keys, or real email fixtures
- no autonomous send, label modification, or draft creation without
  `human_approved`
- no direct `filing_rules` writes outside LearningAgent flows
