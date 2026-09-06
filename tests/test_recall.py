"""Any-overlap recall at its boundaries: touching, crossing, spanning three chunks,
and doc-aware overlap for cross-document gold spans.

Spans are half-open [start, end), matching the chunker's `text[start:end]`
convention -- two spans that only touch at an edge share zero characters.
"""

from __future__ import annotations

from raglab.evals.recall import any_overlap, chunk_id_doc, mrr, recall_at_k, score_retrieval, spans_overlap

# Three contiguous, non-overlapping chunks: [0,10), [10,20), [20,30).
CHUNK_1 = (0, 10)
CHUNK_2 = (10, 20)
CHUNK_3 = (20, 30)


def test_chunk_id_doc_splits_on_last_colon():
    assert chunk_id_doc("fb_rules.pdf:0042") == "fb_rules.pdf"
    assert chunk_id_doc("smg.md:0000") == "smg.md"


def test_gold_span_exactly_meeting_chunk_edge_is_not_a_hit():
    """Gold span [10, 20) touches CHUNK_1's edge at 10 but shares no character."""
    gold_span = (10, 20)
    assert not spans_overlap(CHUNK_1, gold_span)


def test_gold_span_crossing_one_boundary_is_a_hit():
    """Gold span [5, 15) crosses the CHUNK_1/CHUNK_2 boundary at 10."""
    gold_span = (5, 15)
    assert spans_overlap(CHUNK_1, gold_span)
    assert spans_overlap(CHUNK_2, gold_span)


def test_gold_span_covering_three_chunks_hits_each():
    gold_span = (5, 25)
    assert spans_overlap(CHUNK_1, gold_span)
    assert spans_overlap(CHUNK_2, gold_span)
    assert spans_overlap(CHUNK_3, gold_span)


def test_any_overlap_true_if_any_gold_span_matches_same_doc():
    gold_spans = [("doc.md", (100, 110)), ("doc.md", (15, 25))]
    assert any_overlap(gold_spans, "doc.md:0001", CHUNK_2)


def test_any_overlap_false_if_no_gold_span_matches():
    gold_spans = [("doc.md", (100, 110)), ("doc.md", (200, 210))]
    assert not any_overlap(gold_spans, "doc.md:0001", CHUNK_2)


def test_any_overlap_false_when_span_matches_but_doc_differs():
    """A cross-document entry's gold span in one document must never
    "hit" a chunk from an unrelated document just because the raw
    character offsets happen to coincide."""
    gold_spans = [("other.md", (10, 20))]
    assert not any_overlap(gold_spans, "doc.md:0001", CHUNK_2)


def test_score_retrieval_ranks_first_hit():
    gold_spans = [("doc.md", (20, 30))]
    retrieved = [("doc.md:0000", CHUNK_1), ("doc.md:0001", CHUNK_2), ("doc.md:0002", CHUNK_3)]
    score = score_retrieval(gold_spans, retrieved)
    assert score.recall_hit is True
    assert score.rank_of_first_hit == 3


def test_score_retrieval_no_hit():
    gold_spans = [("doc.md", (1000, 1010))]
    retrieved = [("doc.md:0000", CHUNK_1), ("doc.md:0001", CHUNK_2)]
    score = score_retrieval(gold_spans, retrieved)
    assert score.recall_hit is False
    assert score.rank_of_first_hit is None


def test_score_retrieval_ignores_hit_in_wrong_document():
    gold_spans = [("a.md", (20, 30))]
    retrieved = [("b.md:0000", CHUNK_1), ("b.md:0001", CHUNK_2), ("b.md:0002", CHUNK_3)]
    score = score_retrieval(gold_spans, retrieved)
    assert score.recall_hit is False


def test_recall_at_k_aggregates_hits():
    assert recall_at_k([True, True, False, True]) == 0.75
    assert recall_at_k([]) is None


def test_mrr_averages_reciprocal_ranks():
    # hit at rank 1 -> 1.0, hit at rank 2 -> 0.5, miss -> 0.0
    assert mrr([1.0, 0.5, 0.0]) == 0.5
    assert mrr([]) is None
