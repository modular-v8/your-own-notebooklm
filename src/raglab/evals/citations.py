"""Citation block parsing and scoring: the chunk ids a pipeline claims to
have relied on, checked with no model involved.

A citation is cheap to verify and expensive to fake: two checks fall out
for free once the payload is a chunk id rather than prose --

- **fabrication**: was the cited chunk actually in the set retrieved for
  this question?
- **precision**: does the cited chunk's span overlap one of the entry's
  gold spans?

Why a delimited block is safe here when the judge's strict-prompt JSON was
not (see plan.md): the judge's parsing broke on free text inside a quoted
rationale -- never JSON's fault, just unescaped prose. A chunk id is a
fixed lexical shape (`fb_rules.pdf:0042`) with no quotes, no newlines, no
user prose. A token that doesn't match that shape isn't a parse failure,
it's a finding: a fabrication.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .locations import CharSpan, GoldSpan
from .recall import chunk_id_doc, spans_overlap

CITATION_BLOCK_RE = re.compile(r"<citations>(.*?)</citations>", re.DOTALL | re.IGNORECASE)
# The exact shape chunker.py's Chunk.chunk_id produces: "<doc>:<ordinal>".
# Anything else is fabricated by construction -- it can never have been a
# real retrieved chunk.
CHUNK_ID_RE = re.compile(r"^[^\s,:]+:\d+$")


def strip_citations_block(text: str) -> str:
    """The prose answer with any <citations> block removed, so the judge
    and the report's `answer` field see clean text."""
    return CITATION_BLOCK_RE.sub("", text).strip()


def parse_citations(text: str) -> list[str] | None:
    """Chunk-id tokens inside a <citations> block, comma- or
    newline-separated. None if no block is present at all -- distinct from
    an empty list, which means a block was found but named nothing."""
    match = CITATION_BLOCK_RE.search(text)
    if match is None:
        return None
    return [token.strip() for token in re.split(r"[,\n]+", match.group(1)) if token.strip()]


@dataclass(frozen=True)
class CitationResult:
    cited: list[str] | None  # None: no citation block found (uncited)
    fabricated: list[str] | None  # None iff cited is None
    citation_precision: float | None  # None: uncited, or no gold spans to check against


def score_citations(
    cited: list[str] | None,
    retrieved: list[str],
    gold_spans: list[GoldSpan],
    chunk_spans: dict[str, CharSpan],
) -> CitationResult:
    if cited is None:
        return CitationResult(cited=None, fabricated=None, citation_precision=None)

    retrieved_set = set(retrieved)
    fabricated = [c for c in cited if not CHUNK_ID_RE.match(c) or c not in retrieved_set]

    if not gold_spans:
        return CitationResult(cited=cited, fabricated=fabricated, citation_precision=None)

    # Precision is checked against every syntactically valid, resolvable
    # cited chunk -- whether or not it was in *this* retrieval's set.
    # Fabrication and precision are deliberately orthogonal checks (see
    # module docstring): a chunk absent from this question's retrieved set
    # can still be a real chunk with a real span elsewhere in the index.
    resolvable = [c for c in cited if CHUNK_ID_RE.match(c) and c in chunk_spans]
    if not resolvable:
        return CitationResult(cited=cited, fabricated=fabricated, citation_precision=None)

    hits = sum(
        1
        for chunk_id in resolvable
        if any(
            chunk_id_doc(chunk_id) == gold_doc and spans_overlap(chunk_spans[chunk_id], gold_span)
            for gold_doc, gold_span in gold_spans
        )
    )
    return CitationResult(cited=cited, fabricated=fabricated, citation_precision=hits / len(resolvable))
