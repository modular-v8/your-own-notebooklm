"""Candidate signal maths on hand-built retrievals (Phase 5, T2.1)."""

from __future__ import annotations

from raglab.retrieval.retriever import RetrievedChunk
from raglab.retrieval.signals import compute_signals

THRESHOLD = 0.35


def _chunk(chunk_id: str, doc: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=chunk_id, doc=doc, char_start=0, char_end=10, text="x", score=score)


def test_empty_retrieval_is_all_zeros():
    signals = compute_signals([], THRESHOLD)
    assert signals.top1 == 0.0
    assert signals.margin == 0.0
    assert signals.spread == 0.0
    assert signals.count_above == 0
    assert signals.doc_agreement == 0


def test_single_chunk_degenerate_case():
    signals = compute_signals([_chunk("a:0", "a.md", 0.8)], THRESHOLD)
    assert signals.top1 == 0.8
    # No second score to compare against -- margin defaults to the full top1.
    assert signals.margin == 0.8
    # top1 == topk with only one chunk, so spread is always zero.
    assert signals.spread == 0.0
    assert signals.count_above == 1
    assert signals.doc_agreement == 1


def test_known_scores_across_multiple_chunks_same_doc():
    chunks = [
        _chunk("a:0", "a.md", 0.9),
        _chunk("a:1", "a.md", 0.7),
        _chunk("a:2", "a.md", 0.2),
    ]
    signals = compute_signals(chunks, THRESHOLD)
    assert signals.top1 == 0.9
    assert signals.margin == 0.9 - 0.7
    assert signals.spread == 0.9 - 0.2
    assert signals.count_above == 2  # 0.9 and 0.7 clear 0.35; 0.2 does not
    assert signals.doc_agreement == 1


def test_doc_agreement_counts_distinct_documents():
    chunks = [
        _chunk("a:0", "a.md", 0.9),
        _chunk("b:0", "b.md", 0.8),
        _chunk("a:1", "a.md", 0.6),
    ]
    signals = compute_signals(chunks, THRESHOLD)
    assert signals.doc_agreement == 2


def test_count_above_zero_when_nothing_clears_threshold():
    chunks = [_chunk("a:0", "a.md", 0.1), _chunk("a:1", "a.md", 0.05)]
    signals = compute_signals(chunks, THRESHOLD)
    assert signals.count_above == 0
