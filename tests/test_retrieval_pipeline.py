"""RetrievalPipeline via FakeProvider: normal answer flow and empty-retrieval refusal."""

from __future__ import annotations

import pytest

from raglab.pipelines.base import Query
from raglab.pipelines.retrieval import NO_RELEVANT_CHUNKS_STOP_REASON, RetrievalPipeline
from raglab.retrieval.retriever import RetrievedChunk
from tests.fakes import FakeProvider, text_completion


class _StubRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self.chunks = chunks
        self.queries: list[str] = []

    def search(self, query: str, k: int = 5, collection: str | None = None) -> list[RetrievedChunk]:
        self.queries.append(query)
        return self.chunks[:k]


def _chunk(chunk_id: str, doc: str, text: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=chunk_id, doc=doc, char_start=0, char_end=len(text), text=text, score=score)


@pytest.mark.asyncio
async def test_answers_from_relevant_chunks_and_records_ids():
    chunks = [
        _chunk("doc.md:0000", "doc.md", "the minimum age is 16", score=0.8),
        _chunk("doc.md:0001", "doc.md", "unrelated text", score=0.6),
    ]
    provider = FakeProvider([text_completion("16 years old.")])
    pipeline = RetrievalPipeline(provider, _StubRetriever(chunks), score_threshold=0.35)

    result = await pipeline.answer(Query(question="What is the minimum age?", doc_hint="doc.md"))

    assert result.answer == "16 years old."
    assert result.retrieved == ["doc.md:0000", "doc.md:0001"]
    assert provider.calls  # the model was actually asked


@pytest.mark.asyncio
async def test_filters_out_chunks_below_threshold():
    chunks = [
        _chunk("doc.md:0000", "doc.md", "relevant", score=0.9),
        _chunk("doc.md:0001", "doc.md", "barely below threshold", score=0.1),
    ]
    provider = FakeProvider([text_completion("answer")])
    pipeline = RetrievalPipeline(provider, _StubRetriever(chunks), score_threshold=0.35)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))
    assert result.retrieved == ["doc.md:0000"]


@pytest.mark.asyncio
async def test_refuses_without_model_call_when_nothing_above_threshold():
    chunks = [_chunk("doc.md:0000", "doc.md", "off topic", score=0.1)]
    provider = FakeProvider([])  # no scripted response: the model must not be called
    pipeline = RetrievalPipeline(provider, _StubRetriever(chunks), score_threshold=0.35)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    assert result.stop_reason == NO_RELEVANT_CHUNKS_STOP_REASON
    assert result.retrieved == []
    assert result.usage.input_tokens == 0
    assert provider.calls == []


@pytest.mark.asyncio
async def test_doc_hint_is_ignored_retrieval_searches_whole_corpus():
    chunks = [_chunk("other.md:0000", "other.md", "from a different document", score=0.9)]
    provider = FakeProvider([text_completion("answer")])
    retriever = _StubRetriever(chunks)
    pipeline = RetrievalPipeline(provider, retriever, score_threshold=0.35)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))
    assert result.retrieved == ["other.md:0000"]
    assert retriever.queries == ["Q?"]
