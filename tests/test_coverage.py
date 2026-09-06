"""Coverage: fraction of an entry's distinct gold spans actually retrieved."""

from __future__ import annotations

from raglab.evals.coverage import score_coverage


def test_coverage_none_without_gold_spans():
    assert score_coverage([], [("doc.md:0000", (0, 10))]) is None


def test_coverage_full_when_every_gold_span_hit():
    gold_spans = [("doc.md", (0, 10)), ("doc.md", (100, 110))]
    retrieved = [("doc.md:0000", (0, 10)), ("doc.md:0001", (100, 110))]
    assert score_coverage(gold_spans, retrieved) == 1.0


def test_coverage_strictly_below_recall_hit_on_multi_anchor_entry():
    """The acceptance criterion this module exists for: any-overlap recall
    is satisfied the moment *one* of several gold spans is retrieved, but
    coverage must come out lower when only some of them were."""
    gold_spans = [("doc.md", (0, 10)), ("doc.md", (100, 110))]
    retrieved = [("doc.md:0000", (0, 10))]  # only the first anchor retrieved
    coverage = score_coverage(gold_spans, retrieved)
    assert coverage == 0.5
    assert coverage < 1.0  # recall_hit would be True here


def test_coverage_zero_when_nothing_retrieved_overlaps():
    gold_spans = [("doc.md", (0, 10))]
    retrieved = [("doc.md:0000", (500, 510))]
    assert score_coverage(gold_spans, retrieved) == 0.0


def test_coverage_ignores_hit_in_wrong_document():
    gold_spans = [("a.md", (0, 10))]
    retrieved = [("b.md:0000", (0, 10))]
    assert score_coverage(gold_spans, retrieved) == 0.0
