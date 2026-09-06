"""Citation block parsing, fabrication, precision, and the uncited path."""

from __future__ import annotations

from raglab.evals.citations import parse_citations, score_citations, strip_citations_block

GOLD_SPANS = [("doc.md", (0, 10))]
CHUNK_SPANS = {"doc.md:0000": (0, 10), "doc.md:0001": (100, 110)}


def test_parse_citations_comma_separated():
    text = "The answer.\n\n<citations>doc.md:0000, doc.md:0001</citations>"
    assert parse_citations(text) == ["doc.md:0000", "doc.md:0001"]


def test_parse_citations_newline_separated():
    text = "The answer.\n\n<citations>doc.md:0000\ndoc.md:0001</citations>"
    assert parse_citations(text) == ["doc.md:0000", "doc.md:0001"]


def test_parse_citations_empty_block_is_empty_list_not_none():
    text = "I cannot answer.\n\n<citations></citations>"
    assert parse_citations(text) == []


def test_parse_citations_no_block_is_none():
    assert parse_citations("Just a plain answer, no citations block at all.") is None


def test_strip_citations_block_leaves_clean_prose():
    text = "The minimum age is 16.\n\n<citations>doc.md:0000</citations>"
    assert strip_citations_block(text) == "The minimum age is 16."


def test_score_citations_uncited_when_no_block():
    result = score_citations(None, ["doc.md:0000"], GOLD_SPANS, CHUNK_SPANS)
    assert result.cited is None
    assert result.fabricated is None
    assert result.citation_precision is None


def test_score_citations_no_fabrication_when_all_retrieved():
    result = score_citations(["doc.md:0000"], ["doc.md:0000"], GOLD_SPANS, CHUNK_SPANS)
    assert result.fabricated == []


def test_score_citations_fabrication_when_not_in_retrieved_set():
    """A chunk id that resolves to a real span but wasn't retrieved *for
    this question* is still fabricated -- the model claimed context it
    wasn't given."""
    result = score_citations(["doc.md:0001"], ["doc.md:0000"], GOLD_SPANS, CHUNK_SPANS)
    assert result.fabricated == ["doc.md:0001"]


def test_score_citations_malformed_id_is_fabricated_not_raised():
    result = score_citations(["not-a-chunk-id"], ["doc.md:0000"], GOLD_SPANS, CHUNK_SPANS)
    assert result.fabricated == ["not-a-chunk-id"]


def test_score_citations_precision_full_when_cited_chunk_overlaps_gold():
    result = score_citations(["doc.md:0000"], ["doc.md:0000"], GOLD_SPANS, CHUNK_SPANS)
    assert result.citation_precision == 1.0


def test_score_citations_precision_zero_when_cited_chunk_misses_gold():
    result = score_citations(["doc.md:0001"], ["doc.md:0000", "doc.md:0001"], GOLD_SPANS, CHUNK_SPANS)
    assert result.citation_precision == 0.0


def test_score_citations_precision_none_without_gold_spans():
    """not-in-document entries: excluded from precision, not scored zero."""
    result = score_citations(["doc.md:0000"], ["doc.md:0000"], [], CHUNK_SPANS)
    assert result.citation_precision is None


def test_score_citations_precision_none_when_no_resolvable_citations():
    result = score_citations(["garbage-id"], ["doc.md:0000"], GOLD_SPANS, CHUNK_SPANS)
    assert result.citation_precision is None


def test_score_citations_precision_ignores_doc_mismatch():
    """A cited chunk whose span coincidentally overlaps a gold span's
    offsets in a *different* document must not count as a precision hit."""
    result = score_citations(["other.md:0000"], ["other.md:0000"], GOLD_SPANS, {"other.md:0000": (0, 10)})
    assert result.citation_precision == 0.0
