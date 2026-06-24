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

The provider adapter contract is:

1. Load account-specific credentials and checkpoints outside specialist agents.
2. Use provider clients to fetch provider-native payloads.
3. Normalize payloads into `RawEmail`.
4. Assemble `EmailThread` objects through provider-neutral ingestion helpers.
5. Store provider checkpoints in `ProviderSyncCheckpoint`, using
   `graph_delta_link` for Microsoft Graph and `gmail_history_id` for Gmail.

Gmail becomes the next provider by implementing the same adapter boundary:
Gmail payloads map to `RawEmail`, Gmail threads map to `EmailThread`, and Gmail
checkpoint state uses `gmail_history_id`. Classification, filing, relationship,
response, and learning agents must not gain Gmail- or Outlook-specific branches.

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
