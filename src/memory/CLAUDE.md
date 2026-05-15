# Memory Module Instructions

## WHAT
This directory owns Supabase vector and relational memory access.

## WHY
Historical knowledge must live in persistent stores, not in accumulated LLM
context. Filing rules require strict write ownership.

## HOW
- Read filing rules through `rule_store`.
- Write filing rules only from LearningAgent-approved flows.
- Retrieve narrow top-k context for agents.
- Keep account/profile IDs on every memory query.

## Do NOT
- Do not run broad cross-account reads by default.
- Do not let FilingAgent write `filing_rules`.
- Do not store unencrypted raw email bodies in memory helpers.
