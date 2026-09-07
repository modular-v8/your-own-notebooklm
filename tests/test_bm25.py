"""Hand-computed BM25 worked example (specs/4-retrieval-optimization T3.1)."""

from __future__ import annotations

import math

import pytest

from raglab.index.store import StoredChunk
from raglab.retrieval.bm25 import BM25Index

# Three six-token documents, deliberately equal length so avg_doc_length
# cancels the length-normalization term and the by-hand arithmetic stays
# simple: dl / avgdl == 1 for every document.
DOCS = [
    StoredChunk("d0", "doc.md", 0, 0, 6, "the cat sat on the mat"),
    StoredChunk("d1", "doc.md", 1, 0, 6, "the dog sat on the log"),
    StoredChunk("d2", "doc.md", 2, 0, 6, "cats and dogs are great pets"),
]


def _hand_idf(n: int, df: int) -> float:
    return math.log((n - df + 0.5) / (df + 0.5) + 1)


def test_reproduces_hand_computed_score():
    index = BM25Index(DOCS)
    hits = index.search("cat", k=3)

    # "cat" appears only in d0 (tf=1, df=1). k1=1.2, b=0.75, dl=avgdl=6, so
    # the length-normalization term is exactly 1 and the ratio collapses to
    # idf * 1 -- see module docstring's worked-example derivation.
    expected_score = _hand_idf(n=3, df=1)

    assert len(hits) == 1
    assert hits[0].chunk_id == "d0"
    assert hits[0].score == pytest.approx(expected_score)


def test_rare_term_outranks_common_term_on_the_same_document():
    index = BM25Index(DOCS)
    # "the" appears in d0 and d1 (df=2, common); "cat" appears only in d0
    # (df=1, rare). Both queries hit d0 -- the rare term must score higher.
    rare_hits = index.search("cat", k=1)
    common_hits = index.search("the", k=1)

    assert rare_hits[0].chunk_id == "d0"
    assert common_hits[0].chunk_id == "d0"
    assert rare_hits[0].score > common_hits[0].score


def test_no_matching_terms_returns_no_hits():
    index = BM25Index(DOCS)
    assert index.search("zebra spaceship", k=3) == []


def test_collection_filter_excludes_non_member_chunks():
    docs = [
        StoredChunk("d0", "doc.md", 0, 0, 6, "the cat sat on the mat", collections=["rules"]),
        StoredChunk("d1", "doc.md", 1, 0, 6, "the cat is also here", collections=["other"]),
    ]
    index = BM25Index(docs)
    hits = index.search("cat", k=5, collection="rules")
    assert [h.chunk_id for h in hits] == ["d0"]
