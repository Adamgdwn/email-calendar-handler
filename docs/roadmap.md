# Roadmap

## Phase 1: Foundation and Single-Account MVP

1. Repository and project scaffolding.
2. Outlook/Microsoft Graph ingestion with OAuth, deduplication, thread assembly,
   per-folder delta sync, and encrypted content storage.
3. Classification agent with metadata-only context and typed JSON output.
4. Relationship graph stored in Supabase relational tables.
5. Filing structure engine with human-confirmed rule branches.
6. Response draft engine with human review and no autonomous sends.
7. Learning loop and feedback ingestion.

## Phase 2: Second Account

Add a second profile and a second provider path. Gmail becomes the next provider
after Outlook is proven. Account isolation, municipal taxonomy, and no persona
bleed across accounts are required before broader use.

## Phase 3: Relationship Enrichment

Add influence propagation, role disambiguation, and relationship context in draft
suggestions.

## Phase 4: Multi-Account UI

Add all target accounts, web UI, onboarding, and PIPEDA compliance review.
