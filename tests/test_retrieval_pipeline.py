"""RetrievalPipeline via FakeProvider: normal answer flow and empty-retrieval refusal."""

from __future__ import annotations

import pytest

from raglab.pipelines.base import ConversationTurn, Query
from raglab.pipelines.retrieval import NO_RELEVANT_CHUNKS_STOP_REASON, RetrievalPipeline
from raglab.retrieval.retriever import RetrievedChunk
from tests.fakes import FakeProvider, text_completion


class _StubRewriter:
    def __init__(self, result: str | None):
        self._result = result
        self.calls: list[tuple[list, str]] = []

    async def rewrite(self, history, question: str) -> str | None:
        self.calls.append((history, question))
        return self._result


class _StubRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self.chunks = chunks
        self.queries: list[str] = []
        self.search_kwargs: list[dict] = []

    def search(self, query: str, k: int = 5, collection: str | None = None, **kwargs) -> list[RetrievedChunk]:
        self.queries.append(query)
        self.search_kwargs.append(kwargs)
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
    assert result.retrieved_scores == [0.8, 0.6]
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
    assert result.retrieved_scores == []
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


@pytest.mark.asyncio
async def test_hybrid_mode_ignores_score_threshold():
    """RRF fused scores aren't cosine similarities -- a fused score far
    below the dense-tuned score_threshold must still be treated as relevant
    in hybrid mode."""
    chunks = [_chunk("doc.md:0000", "doc.md", "relevant", score=0.02)]  # far below any dense threshold
    provider = FakeProvider([text_completion("answer")])
    pipeline = RetrievalPipeline(
        provider, _StubRetriever(chunks), score_threshold=0.35, mode="hybrid", candidate_k=20
    )

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    assert result.retrieved == ["doc.md:0000"]
    assert provider.calls


@pytest.mark.asyncio
async def test_hybrid_mode_refuses_when_retriever_returns_nothing():
    provider = FakeProvider([])
    pipeline = RetrievalPipeline(provider, _StubRetriever([]), mode="hybrid", candidate_k=20)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    assert result.stop_reason == NO_RELEVANT_CHUNKS_STOP_REASON
    assert provider.calls == []


@pytest.mark.asyncio
async def test_hybrid_mode_passes_mode_and_candidate_k_to_retriever():
    chunks = [_chunk("doc.md:0000", "doc.md", "relevant", score=0.02)]
    provider = FakeProvider([text_completion("answer")])
    retriever = _StubRetriever(chunks)
    pipeline = RetrievalPipeline(provider, retriever, mode="hybrid", candidate_k=20, rrf_k=60)

    await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    kwargs = retriever.search_kwargs[0]
    assert kwargs["mode"] == "hybrid"
    assert kwargs["candidate_k"] == 20
    assert kwargs["rrf_k"] == 60


@pytest.mark.asyncio
async def test_reranking_ignores_score_threshold():
    """A cross-encoder's rerank score also isn't cosine-scale -- same
    bypass as hybrid mode."""
    chunks = [_chunk("doc.md:0000", "doc.md", "relevant", score=-11.0)]  # a plausible cross-encoder logit
    provider = FakeProvider([text_completion("answer")])
    pipeline = RetrievalPipeline(
        provider, _StubRetriever(chunks), score_threshold=0.35, candidate_k=20, reranker=object()
    )

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    assert result.retrieved == ["doc.md:0000"]
    assert provider.calls


@pytest.mark.asyncio
async def test_reranker_and_candidate_k_passed_to_retriever_in_dense_mode():
    chunks = [_chunk("doc.md:0000", "doc.md", "relevant", score=1.0)]
    provider = FakeProvider([text_completion("answer")])
    retriever = _StubRetriever(chunks)
    reranker = object()
    pipeline = RetrievalPipeline(provider, retriever, candidate_k=20, reranker=reranker)

    await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    kwargs = retriever.search_kwargs[0]
    assert kwargs["candidate_k"] == 20
    assert kwargs["reranker"] is reranker


@pytest.mark.asyncio
async def test_no_rewriter_leaves_query_unchanged_and_field_none():
    chunks = [_chunk("doc.md:0000", "doc.md", "relevant", score=0.9)]
    provider = FakeProvider([text_completion("answer")])
    retriever = _StubRetriever(chunks)
    pipeline = RetrievalPipeline(provider, retriever, score_threshold=0.35)

    result = await pipeline.answer(Query(question="Q?", doc_hint="doc.md"))

    assert retriever.queries == ["Q?"]
    assert result.rewritten_query is None


@pytest.mark.asyncio
async def test_rewriter_fires_on_follow_up_and_search_uses_rewritten_query():
    chunks = [_chunk("doc.md:0000", "doc.md", "relevant", score=0.9)]
    provider = FakeProvider([text_completion("answer")])
    retriever = _StubRetriever(chunks)
    history = [ConversationTurn(question="Q1?", answer="A1.")]
    rewriter = _StubRewriter("resolved standalone question")
    pipeline = RetrievalPipeline(provider, retriever, score_threshold=0.35, rewriter=rewriter)

    result = await pipeline.answer(Query(question="what about that?", doc_hint="doc.md", history=history))

    assert retriever.queries == ["resolved standalone question"]
    assert result.rewritten_query == "resolved standalone question"
    assert rewriter.calls == [(history, "what about that?")]


@pytest.mark.asyncio
async def test_rewriter_noop_on_standalone_question_search_uses_original():
    chunks = [_chunk("doc.md:0000", "doc.md", "relevant", score=0.9)]
    provider = FakeProvider([text_completion("answer")])
    retriever = _StubRetriever(chunks)
    rewriter = _StubRewriter(None)  # QueryRewriter's own no-op contract: empty history -> None
    pipeline = RetrievalPipeline(provider, retriever, score_threshold=0.35, rewriter=rewriter)

    result = await pipeline.answer(Query(question="standalone question", doc_hint="doc.md"))

    assert retriever.queries == ["standalone question"]
    assert result.rewritten_query is None


@pytest.mark.asyncio
async def test_rewritten_query_recorded_even_on_refusal():
    provider = FakeProvider([])
    retriever = _StubRetriever([])
    history = [ConversationTurn(question="Q1?", answer="A1.")]
    rewriter = _StubRewriter("resolved standalone question")
    pipeline = RetrievalPipeline(provider, retriever, rewriter=rewriter)

    result = await pipeline.answer(Query(question="what about that?", doc_hint="doc.md", history=history))

    assert result.stop_reason == NO_RELEVANT_CHUNKS_STOP_REASON
    assert result.rewritten_query == "resolved standalone question"
