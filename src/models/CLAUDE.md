# Model Module Instructions

## WHAT
This directory defines Pydantic contracts for email, filing, personas, feedback,
and agent state.

## WHY
Typed contracts stop malformed LLM output or ad hoc dicts from poisoning later
pipeline stages.

## HOW
- Prefer explicit enums and constrained fields.
- Use timezone-aware datetimes.
- Keep model names PascalCase and field names snake_case.
- Add tests for validation rules when schemas change.

## Do NOT
- Do not use raw dicts as public agent inputs or outputs.
- Do not make fields optional to avoid fixing callers.
- Do not store secrets or real email fixture content in models/tests.
