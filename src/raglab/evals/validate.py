"""Heuristic warning: a not-in-document entry whose answer might actually be there.

`sources: []` gives `resolve_gold_locations` nothing to check for a
not-in-document entry -- the exact gap that let the original q-027 and
q-028 (fb_rules.yaml) sit miscategorized until manual review caught them.
This is a lexical overlap heuristic, not a re-verification: it flags lines
worth a human look, and never blocks `gold validate` on its own.
"""

from __future__ import annotations

import re

from ..parsers.registry import ExtractedDocument
from .goldset import NOT_IN_DOCUMENT_TAG, GoldSet

# Short, generic words that would match almost any line and tell an author
# nothing about whether this specific claim is really absent.
STOPWORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "of", "to",
        "in", "on", "for", "and", "or", "what", "which", "how", "does", "do",
        "did", "that", "this", "with", "at", "by", "from", "as", "must", "can",
        "will", "its", "it", "their", "there", "any", "all", "when", "where",
        "who", "whom", "if", "required", "have", "has", "not", "you", "your",
    }
)

MIN_TERM_LENGTH = 4
# A line sharing this many salient question-terms is unlikely to be
# coincidental -- tuned against the reintroduced q-027 (6 shared terms on
# its answer line) while staying quiet on genuinely absent entries.
MIN_SHARED_TERMS = 4
MAX_LINES_PER_WARNING = 5

WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _keywords(question: str) -> set[str]:
    words = WORD_RE.findall(question.lower())
    return {w for w in words if len(w) >= MIN_TERM_LENGTH and w not in STOPWORDS}


def _strong_match_lines(keywords: set[str], text: str) -> list[int]:
    if len(keywords) < MIN_SHARED_TERMS:
        return []
    lines = []
    for i, line in enumerate(text.splitlines(), start=1):
        line_words = set(WORD_RE.findall(line.lower()))
        if len(keywords & line_words) >= MIN_SHARED_TERMS:
            lines.append(i)
    return lines


def check_not_in_document_lexical_matches(
    gold: GoldSet, extracted: dict[str, ExtractedDocument]
) -> list[str]:
    """One warning per (entry, document) with a strong lexical match, naming
    the matching line numbers. Never raises -- a warning, not a rejection,
    since a shared-vocabulary line is a hint, not proof."""
    warnings: list[str] = []
    for entry in gold.entries:
        if NOT_IN_DOCUMENT_TAG not in entry.tags:
            continue
        keywords = _keywords(entry.question)
        for doc_name, extracted_doc in extracted.items():
            lines = _strong_match_lines(keywords, extracted_doc.text)
            if not lines:
                continue
            shown = ", ".join(str(line) for line in lines[:MAX_LINES_PER_WARNING])
            more = f" (+{len(lines) - MAX_LINES_PER_WARNING} more)" if len(lines) > MAX_LINES_PER_WARNING else ""
            warnings.append(
                f"{entry.id}: tagged {NOT_IN_DOCUMENT_TAG!r} but {doc_name} has strong lexical "
                f"matches at line(s) {shown}{more} -- verify this is really not-in-document"
            )
    return warnings
