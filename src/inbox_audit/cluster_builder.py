"""Deterministic clustering of message metadata rows for inbox audit.

No LLM, no I/O. Groups rows by sender domain, tallies folder utilization,
and extracts top subject keywords — entirely from metadata, never from bodies.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from src.models.audit_models import ClusterGroup, ClusterSummary, FolderNode, MessageMetadataRow

_TOP_DOMAINS = 30
_TOP_KEYWORDS = 5

_STOPWORDS = frozenset(
    {
        "re",
        "fwd",
        "fw",
        "the",
        "a",
        "an",
        "in",
        "of",
        "to",
        "and",
        "for",
        "is",
        "on",
        "at",
        "with",
        "your",
        "you",
        "from",
        "our",
        "this",
        "that",
        "we",
        "i",
        "it",
        "be",
        "by",
        "or",
        "as",
        "not",
        "but",
        "if",
        "so",
        "new",
        "has",
        "have",
        "will",
        "can",
        "no",
        "do",
        "up",
        "out",
        "about",
        "please",
        "hi",
        "hello",
        "dear",
        "thanks",
        "thank",
        "regarding",
        "are",
        "was",
        "were",
        "been",
        "its",
        "my",
        "me",
        "us",
        "they",
    }
)


class ClusterBuilder:
    def build(
        self,
        rows: list[MessageMetadataRow],
        folder_tree: list[FolderNode],
        account_email: str,
        months_scanned: int,
    ) -> ClusterSummary:
        total_folders = _count_folders(folder_tree)
        folder_utilization = _build_folder_utilization(rows)
        domain_clusters = _build_domain_clusters(rows)
        keyword_clusters = _build_keyword_clusters(rows)
        return ClusterSummary(
            account_email=account_email,
            months_scanned=months_scanned,
            total_messages=len(rows),
            total_folders=total_folders,
            current_folder_tree=folder_tree,
            domain_clusters=domain_clusters,
            folder_utilization=folder_utilization,
            subject_keyword_clusters=keyword_clusters,
        )


def _count_folders(nodes: list[FolderNode]) -> int:
    return sum(1 + _count_folders(n.child_folders) for n in nodes)


def _build_folder_utilization(rows: list[MessageMetadataRow]) -> dict[str, int]:
    util: Counter[str] = Counter()
    for row in rows:
        util["/".join(row.folder_path)] += 1
    return dict(util.most_common())


def _dominant_folder(rows: list[MessageMetadataRow]) -> str:
    if not rows:
        return ""
    folder_counter: Counter[str] = Counter("/".join(r.folder_path) for r in rows)
    return folder_counter.most_common(1)[0][0]


def _build_domain_clusters(rows: list[MessageMetadataRow]) -> list[ClusterGroup]:
    domain_rows: dict[str, list[MessageMetadataRow]] = defaultdict(list)
    for row in rows:
        domain_rows[row.sender_domain].append(row)

    by_count = sorted(domain_rows.items(), key=lambda x: len(x[1]), reverse=True)
    top = by_count[:_TOP_DOMAINS]
    rest = by_count[_TOP_DOMAINS:]

    clusters = [
        ClusterGroup(
            label=domain,
            dominant_folder=_dominant_folder(domain_row_list),
            message_count=len(domain_row_list),
            sample_subjects=[r.subject_prefix for r in domain_row_list[:5]],
        )
        for domain, domain_row_list in top
    ]
    if rest:
        other_rows = [r for _, dr in rest for r in dr]
        clusters.append(
            ClusterGroup(
                label="other",
                dominant_folder=_dominant_folder(other_rows),
                message_count=len(other_rows),
                sample_subjects=[r.subject_prefix for r in other_rows[:5]],
            )
        )
    return clusters


def _build_keyword_clusters(rows: list[MessageMetadataRow]) -> list[ClusterGroup]:
    word_rows: dict[str, list[MessageMetadataRow]] = defaultdict(list)
    for row in rows:
        words = {w.lower().strip(".,!?;:\"'()[]{}") for w in row.subject_prefix.split()}
        for word in words:
            if word and word not in _STOPWORDS and word.isalpha() and len(word) > 2:
                word_rows[word].append(row)

    top_words = sorted(word_rows.items(), key=lambda x: len(x[1]), reverse=True)[:_TOP_KEYWORDS]
    return [
        ClusterGroup(
            label=keyword,
            dominant_folder=_dominant_folder(kw_rows),
            message_count=len(kw_rows),
            sample_subjects=[r.subject_prefix for r in kw_rows[:5]],
        )
        for keyword, kw_rows in top_words
    ]
