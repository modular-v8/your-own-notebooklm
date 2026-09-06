"""Skip/error/ungraded paths and aggregate math, all against FakeProvider."""

from __future__ import annotations

import pytest

from raglab.corpus import hash_bytes
from raglab.evals.goldset import AnswerLocation, GoldEntry, GoldSet, Source, Turn
from raglab.evals.judge import Judge
from raglab.evals.metrics import compute_aggregates
from raglab.evals.runner import EvalRunner
from raglab.pipelines.whole_doc import WholeDocPipeline
from tests.fakes import FakeProvider, text_completion

DOC_TEXT = "hello"
BIG_DOC_TEXT = "x" * 2000
DOCUMENTS = {"doc.md": DOC_TEXT, "big.md": BIG_DOC_TEXT}


def _gold(*entries: GoldEntry) -> GoldSet:
    corpus_hashes = {name: hash_bytes(text.encode()) for name, text in DOCUMENTS.items()}
    return GoldSet(version=3, collection="everything", corpus_hashes=corpus_hashes, entries=list(entries))


NORMAL_ENTRY = GoldEntry(
    id="q-001",
    turns=[Turn(question="What is X?")],
    expected_answer="Y",
    sources=[Source(doc="doc.md", answer_location=AnswerLocation(type="line_range", start=1, end=2))],
    tags=[],
)
NOT_IN_DOC_ENTRY = GoldEntry(
    id="q-002",
    turns=[Turn(question="What is Z?")],
    expected_answer=None,
    sources=[],
    tags=["not-in-document"],
)
OVER_CONTEXT_ENTRY = GoldEntry(
    id="q-003",
    turns=[Turn(question="What is W?")],
    expected_answer="Y",
    sources=[Source(doc="big.md", answer_location=AnswerLocation(type="line_range", start=1, end=2))],
    tags=[],
)


@pytest.mark.asyncio
async def test_normal_entry_graded_grounded():
    answer_provider = FakeProvider([text_completion("X is Y, per the document.")])
    judge_provider = FakeProvider([text_completion('{"verdict": "grounded", "rationale": "matches"}')])
    runner = EvalRunner(
        WholeDocPipeline(answer_provider, DOCUMENTS),
        Judge(judge_provider),
        _gold(NORMAL_ENTRY),
    )
    result = await runner.run()
    [entry] = result.entries
    assert entry.status == "graded"
    assert entry.verdict == "grounded"
    assert entry.retrieved is None
    assert entry.recall_hit is None


@pytest.mark.asyncio
async def test_not_in_document_entry_uses_refusal_rubric():
    answer_provider = FakeProvider([text_completion("I cannot answer that from the document.")])
    judge_provider = FakeProvider([text_completion('{"verdict": "refused_correctly", "rationale": "declined"}')])
    runner = EvalRunner(
        WholeDocPipeline(answer_provider, DOCUMENTS),
        Judge(judge_provider),
        _gold(NOT_IN_DOC_ENTRY),
    )
    [entry] = (await runner.run()).entries
    assert entry.status == "graded"
    assert entry.verdict == "refused_correctly"


@pytest.mark.asyncio
async def test_not_in_document_entry_answered_against_primary_doc():
    """A not-in-document entry names no source doc of its own -- the
    runner must fall back to the gold set's primary document so the
    whole-doc baseline still has something to put in context."""
    answer_provider = FakeProvider(
        [text_completion("X is Y."), text_completion("I cannot answer that from the document.")]
    )
    judge_provider = FakeProvider(
        [
            text_completion('{"verdict": "grounded", "rationale": "ok"}'),
            text_completion('{"verdict": "refused_correctly", "rationale": "declined"}'),
        ]
    )
    pipeline = WholeDocPipeline(answer_provider, DOCUMENTS)
    runner = EvalRunner(pipeline, Judge(judge_provider), _gold(NORMAL_ENTRY, NOT_IN_DOC_ENTRY))
    result = await runner.run()
    assert all(e.status == "graded" for e in result.entries)


@pytest.mark.asyncio
async def test_over_context_document_is_skipped_not_truncated():
    answer_provider = FakeProvider([], context_window=100)
    judge_provider = FakeProvider([])
    runner = EvalRunner(
        WholeDocPipeline(answer_provider, DOCUMENTS),
        Judge(judge_provider),
        _gold(OVER_CONTEXT_ENTRY),
    )
    [entry] = (await runner.run()).entries
    assert entry.status == "skipped"
    assert entry.answer is None


@pytest.mark.asyncio
async def test_provider_failure_is_errored_not_raised():
    class BoomProvider(FakeProvider):
        async def complete(self, *args, **kwargs):
            raise RuntimeError("provider exploded")

    answer_provider = BoomProvider([], context_window=100_000)
    judge_provider = FakeProvider([])
    runner = EvalRunner(
        WholeDocPipeline(answer_provider, DOCUMENTS),
        Judge(judge_provider),
        _gold(NORMAL_ENTRY),
    )
    [entry] = (await runner.run()).entries
    assert entry.status == "errored"
    assert "provider exploded" in entry.error


@pytest.mark.asyncio
async def test_safety_refusal_is_ungraded_and_skips_judge():
    answer_provider = FakeProvider([text_completion("I won't help with that.", stop_reason="refusal")])
    judge_provider = FakeProvider([])  # no scripted response: judge must not be called
    runner = EvalRunner(
        WholeDocPipeline(answer_provider, DOCUMENTS),
        Judge(judge_provider),
        _gold(NORMAL_ENTRY),
    )
    [entry] = (await runner.run()).entries
    assert entry.status == "ungraded"
    assert judge_provider.calls == []


@pytest.mark.asyncio
async def test_aggregates_across_mixed_outcomes():
    answer_provider = FakeProvider(
        [
            text_completion("X is Y."),
            text_completion("I cannot answer that."),
        ],
        context_window=100_000,
    )
    judge_provider = FakeProvider(
        [
            text_completion('{"verdict": "grounded", "rationale": "ok"}'),
            text_completion('{"verdict": "refused_correctly", "rationale": "ok"}'),
        ]
    )
    runner = EvalRunner(
        WholeDocPipeline(answer_provider, DOCUMENTS),
        Judge(judge_provider),
        _gold(NORMAL_ENTRY, NOT_IN_DOC_ENTRY),
    )
    result = await runner.run()
    aggregates = compute_aggregates(result.entries, result.reciprocal_ranks)
    assert aggregates.graded == 2
    assert aggregates.grounded_rate == 1.0
    assert aggregates.refusal_correct_rate == 1.0
    assert aggregates.recall_at_k is None  # whole_doc pipeline never retrieves
    assert aggregates.mrr is None


@pytest.mark.asyncio
async def test_cross_document_entry_skipped_by_whole_doc_pipeline():
    cross_doc_entry = GoldEntry(
        id="q-004",
        turns=[Turn(question="Cross-doc question")],
        expected_answer="Answer spanning both.",
        sources=[
            Source(doc="doc.md", answer_location=AnswerLocation(type="line_range", start=1, end=1)),
            Source(doc="big.md", answer_location=AnswerLocation(type="line_range", start=1, end=1)),
        ],
        tags=["cross-document"],
    )
    answer_provider = FakeProvider([])
    judge_provider = FakeProvider([])
    runner = EvalRunner(
        WholeDocPipeline(answer_provider, DOCUMENTS),
        Judge(judge_provider),
        _gold(cross_doc_entry),
    )
    [entry] = (await runner.run()).entries
    assert entry.status == "skipped"
    assert "cross-document" in entry.error
    assert answer_provider.calls == []
