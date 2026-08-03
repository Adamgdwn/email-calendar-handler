"""Single-call Anthropic synthesis of folder audit proposals.

Receives a compact ClusterSummary as plain-text tables, never raw email
content. Validates the LLM response as a FolderAuditProposal; raises
AuditSynthesisError on any schema or parse failure.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import ValidationError

from src.llm.anthropic_client import LLMClient, LLMResponse
from src.models.audit_models import ClusterSummary, FolderAuditProposal

_MAX_TOKENS = 2_000

_SCHEMA_HINT = (
    "{\n"
    '  "proposed_tree": [\n'
    '    {"path": ["FolderA", "Sub"], "rationale": "...", '
    '"source_folders": ["OldFolder"], "estimated_volume": 42}\n'
    "  ],\n"
    '  "folders_to_retire": ["OldFolder"],\n'
    '  "folders_to_keep": ["Inbox"],\n'
    '  "key_changes": ["Consolidated X folders into Y"],\n'
    '  "implementation_note": "Move mail manually or use Outlook rules."\n'
    "}"
)


class AuditSynthesisError(ValueError):
    """Raised when the LLM response cannot be validated as a FolderAuditProposal."""


class AuditSynthesizer:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def synthesize(self, summary: ClusterSummary) -> tuple[FolderAuditProposal, LLMResponse]:
        """Return (proposal, llm_response) so callers can log token cost."""
        system = _build_system()
        user = _build_user(summary)
        response = self._llm.complete(system=system, user=user, max_tokens=_MAX_TOKENS)
        proposal = _parse_proposal(response.text, summary.account_email)
        return proposal, response


def _build_system() -> str:
    return (
        "You are a filing system consultant for a busy professional.\n"
        "Analyze the inbox structure data provided and propose an efficient folder hierarchy.\n"
        "Constraints:\n"
        "- Maximum 3 levels of folder depth.\n"
        "- Maximum 15 top-level folders.\n"
        "- Consolidate rarely-used folders; keep the structure simple.\n"
        "Respond with a single JSON object only — no markdown fences, no explanation.\n"
        f"The JSON must match exactly this schema:\n{_SCHEMA_HINT}"
    )


def _build_user(summary: ClusterSummary) -> str:
    lines: list[str] = [
        "INBOX STRUCTURE ANALYSIS",
        f"Account: {summary.account_email}",
        (
            f"Period: {summary.months_scanned} months | "
            f"{summary.total_messages:,} messages | {summary.total_folders} folders"
        ),
        "",
        "CURRENT FOLDER TREE",
    ]
    for node in summary.current_folder_tree:
        lines.append(f"  {node.display_name} ({node.message_count} messages)")
        for child in node.child_folders:
            lines.append(f"    {child.display_name} ({child.message_count} messages)")

    lines += ["", "DOMAIN FREQUENCY (top clusters)", "Domain | Messages | Dominant Folder"]
    for cluster in summary.domain_clusters[:15]:
        lines.append(f"  {cluster.label} | {cluster.message_count} | {cluster.dominant_folder}")

    lines += ["", "FOLDER UTILIZATION (top 20)", "Path | Messages"]
    for path, count in sorted(summary.folder_utilization.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"  {path} | {count}")

    lines += ["", "SUBJECT KEYWORD CLUSTERS", "Keyword | Messages | Dominant Folder"]
    for cluster in summary.subject_keyword_clusters:
        lines.append(f"  {cluster.label} | {cluster.message_count} | {cluster.dominant_folder}")

    return "\n".join(lines)


def _parse_proposal(text: str, account_email: str) -> FolderAuditProposal:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.startswith("```")).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"LLM returned non-JSON response: {exc}"
        raise AuditSynthesisError(msg) from exc
    if not isinstance(data, dict):
        raise AuditSynthesisError("LLM response is not a JSON object")
    data["account_email"] = account_email
    data["generated_at"] = datetime.now(UTC).isoformat()
    try:
        return FolderAuditProposal.model_validate(data)
    except ValidationError as exc:
        msg = f"LLM response does not match FolderAuditProposal schema: {exc}"
        raise AuditSynthesisError(msg) from exc
