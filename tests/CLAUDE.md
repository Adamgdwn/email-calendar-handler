# Test Instructions

## WHAT
Tests prove each milestone before code is committed or published.

## WHY
This project handles sensitive email workflows; plausible code is not enough.

## HOW
- Use pytest.
- Prefer anonymized fixtures and synthetic examples.
- Test Pydantic contracts directly.
- Keep smoke tests fast enough for pre-commit.

## Do NOT
- Do not include real personal email content.
- Do not mock Pydantic models.
- Do not skip approval-gate assertions.
