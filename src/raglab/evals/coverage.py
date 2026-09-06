"""Coverage: the fraction of an entry's distinct gold spans hit by at least
one retrieved chunk.

Recall (recall.py) asks a single yes/no question -- was *any* gold span
hit -- which flatters multi-anchor entries: fb_rules q-004/005/006 each
carry two anchors today, and any-overlap recall calls it a hit the moment
either one is retrieved. Coverage counts how many of the entry's spans
were actually retrieved, so it can (and, per plan.md's acceptance
threshold, must) come out strictly lower than recall_hit on at least one
such entry. It is additive, not a replacement -- the frozen any-overlap
rule (recall.py) is untouched.
"""

from __future__ import annotations

from .locations import CharSpan, GoldSpan
from .recall import chunk_id_doc, spans_overlap


def score_coverage(gold_spans: list[GoldSpan], retrieved: list[tuple[str, CharSpan]]) -> float | None:
    """`retrieved` is (chunk_id, char_span) pairs, order irrelevant here.

    None when the entry has no gold spans (not-in-document, or unscoreable
    for ambiguity) -- there is nothing to compute coverage over.
    """
    if not gold_spans:
        return None

    hit_count = 0
    for gold_doc, gold_span in gold_spans:
        hit = any(
            chunk_id_doc(chunk_id) == gold_doc and spans_overlap(gold_span, chunk_span)
            for chunk_id, chunk_span in retrieved
        )
        if hit:
            hit_count += 1
    return hit_count / len(gold_spans)
