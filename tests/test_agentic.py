"""AgenticPipeline via FakeProvider's simulated tool loop (specs/4-retrieval-
optimization T7.1/T7.2)."""

from __future__ import annotations

import pytest

from raglab.pipelines.agentic import AgenticPipeline
from raglab.pipelines.base import Query
from raglab.retrieval.retriever import RetrievedChunk
from tests.fakes import FakeProvider, ScriptedToolCall, text_completion


def _chunk(chunk_id: str, doc: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=chunk_id, doc=doc, char_start=0, char_end=len(text), text=text, score=0.9)


class _StubRetriever:
    def __init__(self, chunks_by_query: dict[str, list[RetrievedChunk]]):
        self._chunks_by_query = chunks_by_query
        self.queries: list[str] = []

    def search(self, query: str, k: int = 5, collection: str | None = None, **kwargs) -> list[RetrievedChunk]:
        self.queries.append(query)
        return self._chunks_by_query.get(query, [])[:k]


@pytest.mark.asyncio
async def test_answers_without_ever_calling_search():
    provider = FakeProvider([text_completion("16 years old. <citations></citations>")])
    pipeline = AgenticPipeline(provider, _StubRetriever({}))

    result = await pipeline.answer(Query(question="What is the minimum age?", doc_hint="doc.md"))

    assert result.answer == "16 years old."
    assert result.retrieval_calls == 0
    assert result.retrieved == []
    assert result.capped is False


@pytest.mark.asyncio
async def test_single_search_then_answer():
    retriever = _StubRetriever({"minimum age": [_chunk("doc.md:0000", "doc.md", "16 years")]})
    provider = FakeProvider(
        [
            ScriptedToolCall("search", {"query": "minimum age"}),
            text_completion("16 years old. <citations>doc.md:0000</citations>"),
        ]
    )
    pipeline = AgenticPipeline(provider, retriever)

    result = await pipeline.answer(Query(question="What is the minimum age?", doc_hint="doc.md"))

    assert result.retrieval_calls == 1
    assert result.retrieved == ["doc.md:0000"]
    assert result.cited == ["doc.md:0000"]
    assert result.capped is False


@pytest.mark.asyncio
async def test_multiple_searches_accumulate_a_deduplicated_retrieved_union():
    retriever = _StubRetriever(
        {
            "first query": [_chunk("doc.md:0000", "doc.md", "a"), _chunk("doc.md:0001", "doc.md", "b")],
            "second query": [_chunk("doc.md:0001", "doc.md", "b"), _chunk("doc.md:0002", "doc.md", "c")],
        }
    )
    provider = FakeProvider(
        [
            ScriptedToolCall("search", {"query": "first query"}),
            ScriptedToolCall("search", {"query": "second query"}),
            text_completion("answer <citations>doc.md:0000, doc.md:0002</citations>"),
        ]
    )
    pipeline = AgenticPipeline(provider, retriever)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    assert result.retrieval_calls == 2
    # Deduplicated union, first-seen order: doc.md:0001 appears in both calls once.
    assert result.retrieved == ["doc.md:0000", "doc.md:0001", "doc.md:0002"]


@pytest.mark.asyncio
async def test_ceiling_enforced_entry_recorded_as_capped_not_errored():
    retriever = _StubRetriever({f"query {i}": [_chunk(f"doc.md:{i:04d}", "doc.md", "x")] for i in range(10)})
    # Script 5 tool calls against a max_calls=3 ceiling: calls 1-3 succeed,
    # calls 4-5 hit the budget-exhausted response and must not search.
    provider = FakeProvider(
        [
            ScriptedToolCall("search", {"query": "query 0"}),
            ScriptedToolCall("search", {"query": "query 1"}),
            ScriptedToolCall("search", {"query": "query 2"}),
            ScriptedToolCall("search", {"query": "query 3"}),
            ScriptedToolCall("search", {"query": "query 4"}),
            text_completion("final answer given what was found <citations>doc.md:0000</citations>"),
        ]
    )
    pipeline = AgenticPipeline(provider, retriever, max_calls=3)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    # The loop terminated (FakeProvider ran out of scripted tool calls and
    # returned the final text) and the entry still has a real answer -- not
    # an exception, not an errored status.
    assert result.answer == "final answer given what was found"
    assert result.capped is True
    assert result.retrieval_calls == 3  # only the first 3 actually searched
    # Calls 4 and 5 hit the ceiling and never reached the retriever.
    assert retriever.queries == ["query 0", "query 1", "query 2"]


@pytest.mark.asyncio
async def test_history_reaches_the_model_as_alternating_messages():
    from raglab.pipelines.base import ConversationTurn

    provider = FakeProvider([text_completion("answer")])
    pipeline = AgenticPipeline(provider, _StubRetriever({}))
    history = [ConversationTurn(question="Q1?", answer="A1.")]

    await pipeline.answer(Query(question="Q2?", doc_hint="doc.md", history=history))

    sent = provider.calls[0]
    assert sent[0].role == "system"
    assert [(m.role, m.content) for m in sent[1:]] == [
        ("user", "Q1?"),
        ("assistant", "A1."),
        ("user", "Q2?"),
    ]
