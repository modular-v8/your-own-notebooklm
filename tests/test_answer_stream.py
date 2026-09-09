"""answer_stream() must produce the same answer as answer() for the same
input -- the eval harness calls answer() and must never move (plan.md)."""

from __future__ import annotations

import pytest

from raglab.pipelines.base import Query
from raglab.pipelines.retrieval import RetrievalPipeline
from raglab.retrieval.retriever import RetrievedChunk
from tests.fakes import FakeProvider, text_completion

CHUNKS = [
    RetrievedChunk(chunk_id="doc.md:0000", doc="doc.md", char_start=0, char_end=20, text="the minimum age is 16", score=0.8),
    RetrievedChunk(chunk_id="doc.md:0001", doc="doc.md", char_start=20, char_end=40, text="unrelated text", score=0.6),
]


class _StubRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self.chunks = chunks

    def search(self, query: str, k: int = 5, collection: str | None = None, **kwargs) -> list[RetrievedChunk]:
        return self.chunks[:k]


async def _accumulate(pipeline: RetrievalPipeline, query: Query):
    text = ""
    result = None
    async for piece in pipeline.answer_stream(query):
        text += piece.text
        if piece.done:
            result = piece.result
    return text, result


@pytest.mark.asyncio
async def test_stream_matches_answer_for_cited_response():
    raw = "16 years old.\n<citations>doc.md:0000</citations>"
    query = Query(question="What is the minimum age?", doc_hint="doc.md")

    direct = await RetrievalPipeline(FakeProvider([text_completion(raw)]), _StubRetriever(CHUNKS)).answer(query)
    streamed_text, streamed_result = await _accumulate(
        RetrievalPipeline(FakeProvider([text_completion(raw)]), _StubRetriever(CHUNKS)), query
    )

    assert streamed_text == direct.answer
    assert streamed_result.answer == direct.answer
    assert streamed_result.cited == direct.cited == ["doc.md:0000"]
    assert streamed_result.retrieved == direct.retrieved


@pytest.mark.asyncio
async def test_stream_matches_answer_when_uncited():
    raw = "16 years old, no citations block here."
    query = Query(question="What is the minimum age?", doc_hint="doc.md")

    direct = await RetrievalPipeline(FakeProvider([text_completion(raw)]), _StubRetriever(CHUNKS)).answer(query)
    streamed_text, streamed_result = await _accumulate(
        RetrievalPipeline(FakeProvider([text_completion(raw)]), _StubRetriever(CHUNKS)), query
    )

    assert streamed_text == direct.answer == raw
    assert streamed_result.cited is None and direct.cited is None


@pytest.mark.asyncio
async def test_stream_never_emits_citations_block_text():
    raw = "Answer prose.\n<citations>doc.md:0000, doc.md:0001</citations>"
    query = Query(question="Q?", doc_hint="doc.md")
    pipeline = RetrievalPipeline(FakeProvider([text_completion(raw)]), _StubRetriever(CHUNKS))

    streamed_text, streamed_result = await _accumulate(pipeline, query)

    assert "<citations>" not in streamed_text
    assert streamed_text == "Answer prose."
    assert streamed_result.cited == ["doc.md:0000", "doc.md:0001"]


@pytest.mark.asyncio
async def test_stream_matches_answer_when_no_relevant_chunks():
    query = Query(question="Q?", doc_hint="doc.md")
    low_score = [RetrievedChunk(chunk_id="doc.md:0000", doc="doc.md", char_start=0, char_end=5, text="x", score=0.01)]

    direct = await RetrievalPipeline(FakeProvider([]), _StubRetriever(low_score)).answer(query)
    streamed_text, streamed_result = await _accumulate(RetrievalPipeline(FakeProvider([]), _StubRetriever(low_score)), query)

    assert streamed_text == direct.answer
    assert streamed_result.stop_reason == direct.stop_reason
