# Architecture

InboxMind uses a supervisor pattern with typed specialist agents.

## Layers

- System context: personas, org templates, global rules in config files.
- Session context: current email batch and active account profile.
- Memory: Supabase relational tables and pgvector decision embeddings.
- Artifacts: filing proposals, draft suggestions, relationship snapshots.
- Retrieval: top-k historical decisions instead of bulk email history.

## Agent Topology

`EmailSupervisor` is the only router. Specialist agents do not call each other.

- `IngestAgent`: provider ingestion and thread assembly boundary.
- `ClassificationAgent`: sender taxonomy and urgency from metadata/excerpt only.
- `RelationshipAgent`: account-scoped contact graph updates.
- `FilingAgent`: filing proposals from classification metadata and rules.
- `ResponseAgent`: human-reviewed draft suggestions with full thread context.
- `LearningAgent`: feedback ingestion and filing rule promotion.

## Data Boundaries

All inter-agent state uses Pydantic models under `src/models`. Full email bodies
are stored only through ingestion/storage paths and are not passed to
classification, filing, or relationship stages.

## Provider Strategy

Milestone 1.2 targets Outlook first through Microsoft Graph. Provider adapters
must map external messages into the same internal Pydantic contracts so later
Gmail support does not fork the downstream pipeline.

Provider-specific checkpoints stay outside agent logic:
- Microsoft Graph stores per-account or per-folder `deltaLink` checkpoints.
- Gmail later stores `historyId` checkpoints.

Agents consume `RawEmail`, `EmailThread`, and `AccountContext` only; they do not
branch on provider unless a typed model explicitly requires it.

## Outlook OAuth Boundary

The first provider uses Microsoft Graph delegated permissions. Configuration is
loaded from environment variables through `MicrosoftGraphOAuthSettings`, and the
initial allowed scope set is `offline_access`, `User.Read`, and `Mail.Read`.
Write-capable mail scopes such as send or read/write are rejected at config
validation time.

Every connected account must log an `OAuthConsentRecord` into `account_consents`
before mailbox sync. Consent records require `human_confirmed: true`.

## Milestone 1.1 Decisions

- Use Python 3.12 and exact dependency pins.
- Use `uv` for affordable, fast local setup.
- Include LangGraph as a dependency, but keep orchestration as typed stubs until
  the pipeline behavior justifies graph wiring.
- Use direct Anthropic SDK integration behind project interfaces in later
  milestones to avoid unnecessary framework cost.
