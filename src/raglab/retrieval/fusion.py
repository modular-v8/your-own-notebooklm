"""Reciprocal Rank Fusion (plan.md Tech Stack): dense cosine and BM25 scores
live on incomparable scales; weighted fusion would need a normalization step
that becomes its own tuned parameter. RRF is rank-based and scale-free,
which removes the problem instead of tuning it. `rrf_k=60` is the constant
from the original paper, not swept.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class FusedResult:
    chunk_id: str
    score: float


def reciprocal_rank_fusion(ranked_lists: list[list[str]], *, rrf_k: int = DEFAULT_RRF_K) -> list[FusedResult]:
    """Each inner list is chunk ids in rank order (best first) from one
    retrieval method. Fused score = sum over lists of 1/(rrf_k + rank), rank
    1-indexed; a chunk absent from a list contributes nothing for that list.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
    # Stable sort: with a single input list, every score is strictly
    # decreasing in rank already, so this is a no-op that preserves order --
    # the degenerate single-list case needs no special handling.
    fused = sorted(scores.items(), key=lambda pair: -pair[1])
    return [FusedResult(chunk_id, score) for chunk_id, score in fused]
