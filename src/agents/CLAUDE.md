# Agent Module Instructions

## WHAT
This directory contains the supervisor and specialist agent boundaries for the
InboxMind pipeline.

## WHY
The supervisor pattern keeps routing auditable. Specialist agents cannot call
each other directly; they receive typed input and return typed output.

## HOW
- Keep every agent single-purpose.
- Use Pydantic models from `src.models` at every boundary.
- Keep system prompt builders small and token-budgeted.
- Make ambiguous external actions return a pending approval object.

## Do NOT
- Do not call another specialist agent from a specialist agent.
- Do not mutate external email state from an agent.
- Do not pass full email bodies to ClassificationAgent, FilingAgent, or
  RelationshipAgent.
- Do not write to filing rules except through LearningAgent.
