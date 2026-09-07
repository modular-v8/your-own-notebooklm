"""Reciprocal Rank Fusion (specs/4-retrieval-optimization T3.2)."""

from __future__ import annotations

import pytest

from raglab.retrieval.fusion import reciprocal_rank_fusion


def test_degenerate_single_list_preserves_order():
    ranked = ["a", "b", "c", "d"]
    fused = reciprocal_rank_fusion([ranked])
    assert [f.chunk_id for f in fused] == ranked


def test_ordering_combines_two_lists():
    dense = ["a", "b", "c"]
    lexical = ["b", "a", "d"]
    fused = reciprocal_rank_fusion([dense, lexical])
    # "a" (rank 1 + rank 2) and "b" (rank 2 + rank 1) tie for the top two
    # spots; "d" (only in lexical, rank 3) and "c" (only in dense, rank 3)
    # tie for last. Both pairs score identically by symmetry.
    ids = [f.chunk_id for f in fused]
    assert set(ids[:2]) == {"a", "b"}
    assert set(ids[2:]) == {"c", "d"}


def test_document_present_in_only_one_list_still_included():
    dense = ["a", "b"]
    lexical = ["c"]
    fused = reciprocal_rank_fusion([dense, lexical])
    assert {f.chunk_id for f in fused} == {"a", "b", "c"}


def test_symmetric_tie_does_not_crash_and_scores_equal():
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])
    scores = {f.chunk_id: f.score for f in fused}
    assert scores["a"] == pytest.approx(scores["b"])


def test_score_is_sum_of_reciprocal_ranks():
    fused = reciprocal_rank_fusion([["a"], ["a"]], rrf_k=60)
    assert fused[0].score == pytest.approx(2 * (1 / 61))
