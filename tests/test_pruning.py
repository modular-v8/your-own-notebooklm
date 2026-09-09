"""Top-N context pruning in AgenticPipeline (Phase 5, T5.1): retain the
top-N accumulated chunks by score across every search call, instead of
their union, and record how many were discarded."""

from __future__ import annotations

import pytest

from raglab.pipelines.agentic import AgenticPipeline
from raglab.pipelines.base import Query
from raglab.retrieval.retriever import RetrievedChunk
from tests.fakes import FakeProvider, ScriptedToolCall, text_completion


def _chunk(chunk_id: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=chunk_id, doc="doc.md", char_start=0, char_end=1, text="x", score=score)


class _StubRetriever:
    def __init__(self, chunks_by_query: dict[str, list[RetrievedChunk]]):
        self._chunks_by_query = chunks_by_query

    def search(self, query: str, k: int = 5, collection: str | None = None, **kwargs) -> list[RetrievedChunk]:
        return self._chunks_by_query.get(query, [])[:k]


@pytest.mark.asyncio
async def test_no_pruning_by_default_keeps_full_union():
    retriever = _StubRetriever({"q1": [_chunk("a", 0.9), _chunk("b", 0.5)]})
    provider = FakeProvider(
        [ScriptedToolCall("search", {"query": "q1"}), text_completion("answer <citations></citations>")]
    )
    pipeline = AgenticPipeline(provider, retriever)  # prune_top_n unset

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    assert result.retrieved == ["a", "b"]
    assert result.pruned_discarded is None


@pytest.mark.asyncio
async def test_pruning_is_a_noop_when_accumulated_set_already_at_or_below_n():
    retriever = _StubRetriever({"q1": [_chunk("a", 0.9), _chunk("b", 0.5)]})
    provider = FakeProvider(
        [ScriptedToolCall("search", {"query": "q1"}), text_completion("answer <citations></citations>")]
    )
    pipeline = AgenticPipeline(provider, retriever, prune_top_n=5)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    assert set(result.retrieved) == {"a", "b"}
    assert result.pruned_discarded == 0


@pytest.mark.asyncio
async def test_pruning_retains_top_n_by_score_and_records_discarded_count():
    retriever = _StubRetriever(
        {
            "first": [_chunk("a", 0.9), _chunk("b", 0.3)],
            "second": [_chunk("c", 0.6), _chunk("d", 0.1)],
        }
    )
    provider = FakeProvider(
        [
            ScriptedToolCall("search", {"query": "first"}),
            ScriptedToolCall("search", {"query": "second"}),
            text_completion("answer <citations></citations>"),
        ]
    )
    pipeline = AgenticPipeline(provider, retriever, prune_top_n=2)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    # 4 accumulated (a=0.9, b=0.3, c=0.6, d=0.1) -> top 2 by score: a, c.
    assert result.retrieved == ["a", "c"]
    assert result.retrieved_scores == [0.9, 0.6]
    assert result.pruned_discarded == 2


@pytest.mark.asyncio
async def test_pruning_does_not_affect_what_the_model_already_saw_mid_conversation():
    # Pruning only trims the *recorded* accumulator for scoring purposes --
    # it can't retroactively change tool results already returned to the
    # model, so retrieval_calls and capped are unaffected by prune_top_n.
    retriever = _StubRetriever({"q1": [_chunk("a", 0.9), _chunk("b", 0.5), _chunk("c", 0.4)]})
    provider = FakeProvider(
        [ScriptedToolCall("search", {"query": "q1"}), text_completion("answer <citations></citations>")]
    )
    pipeline = AgenticPipeline(provider, retriever, prune_top_n=1)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    assert result.retrieval_calls == 1
    assert result.retrieved == ["a"]
    assert result.pruned_discarded == 2
