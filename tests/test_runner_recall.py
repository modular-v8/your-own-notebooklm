"""EvalRunner's recall/MRR wiring: a pipeline that retrieves gets scored, one that doesn't stays null."""

from __future__ import annotations

import pytest

from raglab.corpus import hash_bytes
from raglab.evals.goldset import AnswerLocation, GoldEntry, GoldSet, Source, Turn
from raglab.evals.judge import Judge
from raglab.evals.metrics import compute_aggregates
from raglab.evals.runner import EvalRunner
from raglab.pipelines.base import PipelineResult, Query
from raglab.providers.base import Usage
from tests.fakes import FakeProvider, text_completion

DOC_TEXT = "chunk zero text here. " * 5 + "chunk one text here. " * 5


class _FakeRetrievalPipeline:
    """Returns a scripted PipelineResult per call, recording which chunk ids it 'retrieved'."""

    name = "fake_retrieval"

    def __init__(self, retrieved_by_entry: dict[str, list[str]]):
        self.retrieved_by_entry = retrieved_by_entry
        self.calls: list[Query] = []

    async def answer(self, query: Query) -> PipelineResult:
        self.calls.append(query)
        entry_id = query.question  # tests key by question text for simplicity
        return PipelineResult(
            answer="the answer",
            stop_reason="end_turn",
            usage=Usage(input_tokens=10, output_tokens=5),
            latency_s=0.01,
            retrieved=self.retrieved_by_entry[entry_id],
        )


def _gold(*entries: GoldEntry) -> GoldSet:
    return GoldSet(
        version=3, collection="everything", corpus_hashes={"doc.md": hash_bytes(DOC_TEXT.encode())}, entries=list(entries)
    )


def _entry(entry_id: str, tags: list[str] | None = None) -> GoldEntry:
    return GoldEntry(
        id=entry_id,
        turns=[Turn(question=entry_id)],
        expected_answer="Y",
        sources=[Source(doc="doc.md", answer_location=AnswerLocation(type="char_span", start=0, end=10))],
        tags=tags or [],
    )


HIT_ENTRY = _entry("q-hit")
MISS_ENTRY = _entry("q-miss")
NOT_IN_DOC_ENTRY = GoldEntry(
    id="q-nid",
    turns=[Turn(question="q-nid")],
    expected_answer=None,
    sources=[],
    tags=["not-in-document"],
)

GOLD_SPANS = {"q-hit": [("doc.md", (0, 10))], "q-miss": [("doc.md", (0, 10))]}
CHUNK_SPANS = {"doc.md:0000": (0, 10), "doc.md:0001": (100, 110), "doc.md:0002": (5, 15)}


@pytest.mark.asyncio
async def test_recall_hit_and_rank_recorded():
    answer_provider = FakeProvider([])
    judge_provider = FakeProvider(
        [text_completion('{"verdict": "grounded", "rationale": "ok"}')] * 1
    )
    pipeline = _FakeRetrievalPipeline({"q-hit": ["doc.md:0001", "doc.md:0002"]})  # hit at rank 2 (doc.md:0002 overlaps)
    runner = EvalRunner(
        pipeline, Judge(judge_provider), _gold(HIT_ENTRY), gold_spans=GOLD_SPANS, chunk_spans=CHUNK_SPANS
    )
    result = await runner.run()
    [entry] = result.entries
    assert entry.retrieved == ["doc.md:0001", "doc.md:0002"]
    assert entry.recall_hit is True
    assert result.reciprocal_ranks == [0.5]  # hit at rank 2


@pytest.mark.asyncio
async def test_recall_miss_recorded():
    judge_provider = FakeProvider([text_completion('{"verdict": "not_grounded", "rationale": "ok"}')])
    pipeline = _FakeRetrievalPipeline({"q-miss": ["doc.md:0001"]})  # no overlap with gold span (0,10)
    runner = EvalRunner(
        pipeline, Judge(judge_provider), _gold(MISS_ENTRY), gold_spans=GOLD_SPANS, chunk_spans=CHUNK_SPANS
    )
    result = await runner.run()
    [entry] = result.entries
    assert entry.recall_hit is False
    assert result.reciprocal_ranks == [0.0]


@pytest.mark.asyncio
async def test_not_in_document_entry_has_null_recall_even_with_retrieval():
    judge_provider = FakeProvider([text_completion('{"verdict": "refused_correctly", "rationale": "ok"}')])
    pipeline = _FakeRetrievalPipeline({"q-nid": ["doc.md:0000"]})
    runner = EvalRunner(
        pipeline, Judge(judge_provider), _gold(NOT_IN_DOC_ENTRY), gold_spans=GOLD_SPANS, chunk_spans=CHUNK_SPANS
    )
    result = await runner.run()
    [entry] = result.entries
    assert entry.retrieved == ["doc.md:0000"]
    assert entry.recall_hit is None  # no gold span to score against
    assert entry.coverage is None
    assert result.reciprocal_ranks == []


@pytest.mark.asyncio
async def test_aggregates_compute_recall_at_k_and_mrr():
    judge_provider = FakeProvider(
        [
            text_completion('{"verdict": "grounded", "rationale": "ok"}'),
            text_completion('{"verdict": "not_grounded", "rationale": "ok"}'),
        ]
    )
    pipeline = _FakeRetrievalPipeline({"q-hit": ["doc.md:0000"], "q-miss": ["doc.md:0001"]})
    runner = EvalRunner(
        pipeline,
        Judge(judge_provider),
        _gold(HIT_ENTRY, MISS_ENTRY),
        gold_spans=GOLD_SPANS,
        chunk_spans=CHUNK_SPANS,
    )
    result = await runner.run()
    aggregates = compute_aggregates(result.entries, result.reciprocal_ranks)
    assert aggregates.recall_at_k == 0.5
    assert aggregates.mrr == 0.5  # (1.0 + 0.0) / 2


@pytest.mark.asyncio
async def test_coverage_recorded_for_multi_anchor_entry():
    """Coverage differs from recall_hit: recall_hit is satisfied by any one
    gold span being retrieved, coverage counts how many were."""
    multi_entry = GoldEntry(
        id="q-multi",
        turns=[Turn(question="q-multi")],
        expected_answer="Y",
        sources=[
            Source(doc="doc.md", answer_location=AnswerLocation(type="char_span", start=0, end=10)),
            Source(doc="doc.md", answer_location=AnswerLocation(type="char_span", start=100, end=110)),
        ],
        tags=[],
    )
    gold_spans = {"q-multi": [("doc.md", (0, 10)), ("doc.md", (100, 110))]}
    judge_provider = FakeProvider([text_completion('{"verdict": "grounded", "rationale": "ok"}')])
    pipeline = _FakeRetrievalPipeline({"q-multi": ["doc.md:0000"]})  # only hits the first gold span
    runner = EvalRunner(
        pipeline, Judge(judge_provider), _gold(multi_entry), gold_spans=gold_spans, chunk_spans=CHUNK_SPANS
    )
    [entry] = (await runner.run()).entries
    assert entry.recall_hit is True
    assert entry.coverage == 0.5
    assert entry.coverage < 1.0
