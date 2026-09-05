"""Any-overlap recall, recall@k, and MRR.

A chunk is a recall hit if its span shares at least one character with a
gold span — frozen here per plan.md, because majority-overlap or
full-containment would move recall when chunk size changes even though
retrieval didn't get worse, and Phase 4 varies chunk size deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass

from .locations import CharSpan


def spans_overlap(a: CharSpan, b: CharSpan) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def any_overlap(gold_spans: list[CharSpan], chunk_span: CharSpan) -> bool:
    return any(spans_overlap(gold_span, chunk_span) for gold_span in gold_spans)


@dataclass(frozen=True)
class RetrievalScore:
    recall_hit: bool
    rank_of_first_hit: int | None  # 1-indexed; None if no retrieved chunk hit


def score_retrieval(gold_spans: list[CharSpan], retrieved: list[tuple[str, CharSpan]]) -> RetrievalScore:
    """`retrieved` is ordered by rank (best first): (chunk_id, char_span) pairs."""
    for rank, (_, span) in enumerate(retrieved, start=1):
        if any_overlap(gold_spans, span):
            return RetrievalScore(recall_hit=True, rank_of_first_hit=rank)
    return RetrievalScore(recall_hit=False, rank_of_first_hit=None)


def recall_at_k(hits: list[bool]) -> float | None:
    return (sum(hits) / len(hits)) if hits else None


def mrr(reciprocal_ranks: list[float]) -> float | None:
    return (sum(reciprocal_ranks) / len(reciprocal_ranks)) if reciprocal_ranks else None
