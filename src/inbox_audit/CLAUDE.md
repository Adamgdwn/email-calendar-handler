# Inbox Audit Module Instructions

## WHAT
This module owns the read-only mailbox audit pipeline: fetch folder tree and
message metadata from Microsoft Graph, cluster deterministically, synthesize a
proposed filing hierarchy via one Anthropic call, and render a Markdown report.

## WHY
Audit reads live Graph API data directly (no Supabase) so it always reflects
the current mailbox state, not the last sync snapshot. The LLM touches only
aggregated statistics — never raw message bodies or subjects directly.

## HOW
- `FolderFetcher` speaks to Graph; inject via the `FolderFetchTransport`
  protocol so tests never hit the network.
- `ClusterBuilder` is pure Python; no LLM, no I/O, fully deterministic.
- `AuditSynthesizer` makes exactly one `LLMClient.complete()` call; inject a
  `FakeLLMClient` in tests.
- `AuditRenderer` writes the Markdown file and prints the terminal summary;
  it never modifies mailbox state.
- All models in `src/models/audit_models.py`.

## Do NOT
- Do not pass raw email bodies or full subject lists into the LLM prompt.
- Do not write to the mailbox or create Graph write calls.
- Do not import from `src/agents/` or `src/memory/` — this module feeds the
  CLI layer only.
