"""Reranker wrapper (specs/4-retrieval-optimization T4.1).

Default-run tests stub `TextCrossEncoder` out entirely, so this file needs
no network and no ONNX runtime work -- consistent with AGENT.md's "no
network access" rule for the default suite. The real-model worked example
(T2.6's own live probe) is re-verified separately, marked integration, the
same way test_embedder.py handles fastembed's dense model.
"""

from __future__ import annotations

import pytest

import raglab.retrieval.reranker as reranker_module
from raglab.retrieval.reranker import DEFAULT_RERANKER_MODEL, Reranker


class _FakeCrossEncoder:
    instances = 0

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.calls: list[tuple[str, list[str]]] = []
        _FakeCrossEncoder.instances += 1

    def rerank(self, query: str, texts: list[str]):
        self.calls.append((query, texts))
        # Deterministic fake score: later texts score lower, so callers can
        # assert on a known, reversed-from-input ordering.
        return list(range(len(texts), 0, -1))


@pytest.fixture(autouse=True)
def _reset_fake_encoder_count():
    _FakeCrossEncoder.instances = 0
    yield


def test_model_loads_once_per_process_not_once_per_query(monkeypatch):
    monkeypatch.setattr(reranker_module, "TextCrossEncoder", _FakeCrossEncoder)
    reranker = Reranker()

    reranker.rerank("q1", [("a", "text a"), ("b", "text b")])
    reranker.rerank("q2", [("a", "text a"), ("b", "text b")])
    reranker.rerank("q3", [("a", "text a"), ("b", "text b")])

    assert _FakeCrossEncoder.instances == 1


def test_rerank_sorts_by_score_descending(monkeypatch):
    monkeypatch.setattr(reranker_module, "TextCrossEncoder", _FakeCrossEncoder)
    reranker = Reranker()

    # Fake scores are len(texts)..1 in input order, so the LAST candidate
    # gets the lowest fake score -- result must come back reordered.
    results = reranker.rerank("q", [("a", "x"), ("b", "y"), ("c", "z")])

    assert [r.chunk_id for r in results] == ["a", "b", "c"]
    assert [r.score for r in results] == [3.0, 2.0, 1.0]


def test_rerank_empty_candidates_returns_empty_without_loading_model(monkeypatch):
    monkeypatch.setattr(reranker_module, "TextCrossEncoder", _FakeCrossEncoder)
    reranker = Reranker()

    assert reranker.rerank("q", []) == []
    assert _FakeCrossEncoder.instances == 0


def test_default_model_name_is_the_t2_6_probed_model():
    assert DEFAULT_RERANKER_MODEL == "Xenova/ms-marco-MiniLM-L-6-v2"


@pytest.mark.integration
def test_real_model_reproduces_t2_6_worked_example():
    """Needs the real, already-cached ONNX model (network on first use) --
    excluded from the default run the same way test_embedder.py is."""
    reranker = Reranker()
    candidates = [
        ("correct", "Team members must be at least 16 years of age."),
        ("irrelevant-1", "The Impact Attenuator must be at least 100 mm high and 200 mm wide."),
        ("irrelevant-2", "Each team must have at least two dry chemical fire extinguishers."),
    ]

    results = reranker.rerank("What is the minimum age for a Formula Bharat team member?", candidates)

    assert results[0].chunk_id == "correct"
    assert results[0].score > results[1].score > results[2].score
