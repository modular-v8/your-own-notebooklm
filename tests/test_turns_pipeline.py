"""Conversation history reaches the model but never the retriever -- the
core Phase 3 measurement asymmetry (specs/3-collections/plan.md)."""

from __future__ import annotations

import pytest

from raglab.corpus import hash_bytes
from raglab.evals.goldset import AnswerLocation, GoldEntry, GoldSet, Source, Turn
from raglab.evals.judge import Judge
from raglab.evals.runner import EvalRunner, _build_query, _expects_refusal
from raglab.pipelines.base import ConversationTurn, PipelineResult, Query
from raglab.pipelines.retrieval import RetrievalPipeline
from raglab.pipelines.whole_doc import WholeDocPipeline
from raglab.providers.base import Usage
from raglab.retrieval.retriever import RetrievedChunk
from tests.fakes import FakeProvider, text_completion


def _chunk(chunk_id: str, text: str, score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=chunk_id, doc="doc.md", char_start=0, char_end=len(text), text=text, score=score)


class _StubRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self.chunks = chunks
        self.calls: list[tuple[str, str | None]] = []

    def search(self, query: str, k: int = 5, collection: str | None = None):
        self.calls.append((query, collection))
        return self.chunks[:k]


HISTORY = [ConversationTurn(question="What is X?", answer="X is Y.")]


@pytest.mark.asyncio
async def test_retrieval_pipeline_sends_history_as_alternating_messages():
    retriever = _StubRetriever([_chunk("doc.md:0000", "relevant text")])
    provider = FakeProvider([text_completion("Final answer.")])
    pipeline = RetrievalPipeline(provider, retriever, score_threshold=0.35)

    await pipeline.answer(Query(question="What about Z?", doc_hint="doc.md", history=HISTORY))

    [messages] = provider.calls
    roles_and_content = [(m.role, m.content) for m in messages]
    assert ("user", "What is X?") in roles_and_content
    assert ("assistant", "X is Y.") in roles_and_content
    # the final user message carries the excerpts + the *current* question
    assert "What about Z?" in messages[-1].content


@pytest.mark.asyncio
async def test_retrieval_pipeline_retrieves_using_only_the_final_question():
    """The deficit this phase measures: retrieval never sees history, even
    though the model does."""
    retriever = _StubRetriever([_chunk("doc.md:0000", "relevant text")])
    provider = FakeProvider([text_completion("Final answer.")])
    pipeline = RetrievalPipeline(provider, retriever, score_threshold=0.35)

    await pipeline.answer(Query(question="What about Z?", doc_hint="doc.md", history=HISTORY, collection="rules"))

    [(query_text, collection)] = retriever.calls
    assert query_text == "What about Z?"
    assert "X is Y" not in query_text
    assert collection == "rules"


@pytest.mark.asyncio
async def test_whole_doc_pipeline_sends_history_as_alternating_messages():
    provider = FakeProvider([text_completion("Final answer.")])
    pipeline = WholeDocPipeline(provider, {"doc.md": "the document text"})

    await pipeline.answer(Query(question="What about Z?", doc_hint="doc.md", history=HISTORY))

    [messages] = provider.calls
    roles_and_content = [(m.role, m.content) for m in messages]
    assert ("user", "What is X?") in roles_and_content
    assert ("assistant", "X is Y.") in roles_and_content


def test_build_query_carries_history_and_collection_from_entry():
    entry = GoldEntry(
        id="q-031",
        turns=[
            Turn(question="What is X?", answer="X is Y."),
            Turn(question="What about Z?"),
        ],
        expected_answer="Z is W.",
        sources=[Source(doc="doc.md", answer_location=AnswerLocation(type="line_range", start=1, end=1))],
        tags=["follow-up"],
    )
    query = _build_query(entry, primary_doc=None, collection="rules")
    assert query.question == "What about Z?"
    assert query.history == [ConversationTurn(question="What is X?", answer="X is Y.")]
    assert query.collection == "rules"


def test_build_query_history_empty_for_standalone_entry():
    entry = GoldEntry(
        id="q-001",
        turns=[Turn(question="What is X?")],
        expected_answer="Y",
        sources=[Source(doc="doc.md", answer_location=AnswerLocation(type="line_range", start=1, end=1))],
        tags=[],
    )
    query = _build_query(entry, primary_doc=None, collection="rules")
    assert query.history == []


@pytest.mark.asyncio
async def test_runner_passes_gold_collection_to_every_query():
    class _RecordingPipeline:
        name = "recording"

        def __init__(self):
            self.queries: list[Query] = []

        async def answer(self, query: Query) -> PipelineResult:
            self.queries.append(query)
            return PipelineResult(
                answer="an answer",
                stop_reason="end_turn",
                usage=Usage(input_tokens=1, output_tokens=1),
                latency_s=0.0,
            )

    entry = GoldEntry(
        id="q-001",
        turns=[Turn(question="What is X?")],
        expected_answer="Y",
        sources=[Source(doc="doc.md", answer_location=AnswerLocation(type="line_range", start=1, end=1))],
        tags=[],
    )
    gold = GoldSet(
        version=3,
        collection="rules",
        corpus_hashes={"doc.md": hash_bytes(b"hello")},
        entries=[entry],
    )
    pipeline = _RecordingPipeline()
    judge_provider = FakeProvider([text_completion('{"verdict": "grounded", "rationale": "ok"}')])
    runner = EvalRunner(pipeline, Judge(judge_provider), gold)
    await runner.run()

    assert pipeline.queries[0].collection == "rules"


COLLECTIONS = {"rules": ["fb_rules.pdf"], "transmissions": ["smg.md"], "everything": ["fb_rules.pdf", "smg.md"]}


def _not_in_collection_entry() -> GoldEntry:
    return GoldEntry(
        id="q-001",
        turns=[Turn(question="In what year did BMW coin SMG?")],
        expected_answer="1996.",
        sources=[Source(doc="smg.md", answer_location=AnswerLocation(type="line_range", start=1, end=1))],
        tags=["not-in-collection"],
    )


def test_expects_refusal_true_when_docs_outside_active_collection():
    """The regression this test guards: the first live scoping.yaml run
    graded a not-in-collection entry with the groundedness rubric instead
    of the refusal rubric, because the runner only recognized
    not-in-document -- every entry failed even though the pipeline
    correctly refused."""
    entry = _not_in_collection_entry()
    assert _expects_refusal(entry, "rules", COLLECTIONS) is True


def test_expects_refusal_false_when_docs_inside_active_collection():
    entry = _not_in_collection_entry()
    assert _expects_refusal(entry, "transmissions", COLLECTIONS) is False
    assert _expects_refusal(entry, "everything", COLLECTIONS) is False


@pytest.mark.asyncio
async def test_runner_grades_not_in_collection_entry_with_refusal_rubric_when_scoped_out():
    class _RefusingPipeline:
        name = "refusing"

        async def answer(self, query: Query) -> PipelineResult:
            return PipelineResult(
                answer="I cannot answer this from the retrieved material.",
                stop_reason="no_relevant_chunks",
                usage=Usage(input_tokens=1, output_tokens=1),
                latency_s=0.0,
                retrieved=[],
            )

    gold = GoldSet(
        version=3, collection="rules", corpus_hashes={"smg.md": hash_bytes(b"x")}, entries=[_not_in_collection_entry()]
    )
    judge_provider = FakeProvider([text_completion('{"verdict": "refused_correctly", "rationale": "declined"}')])
    runner = EvalRunner(
        _RefusingPipeline(), Judge(judge_provider), gold, collection="rules", collections=COLLECTIONS
    )
    [entry_report] = (await runner.run()).entries
    assert entry_report.verdict == "refused_correctly"


@pytest.mark.asyncio
async def test_runner_grades_not_in_collection_entry_with_groundedness_rubric_when_scoped_in():
    class _AnsweringPipeline:
        name = "answering"

        async def answer(self, query: Query) -> PipelineResult:
            return PipelineResult(
                answer="1996.",
                stop_reason="end_turn",
                usage=Usage(input_tokens=1, output_tokens=1),
                latency_s=0.0,
                retrieved=["smg.md:0000"],
            )

    gold = GoldSet(
        version=3, collection="rules", corpus_hashes={"smg.md": hash_bytes(b"x")}, entries=[_not_in_collection_entry()]
    )
    judge_provider = FakeProvider([text_completion('{"verdict": "grounded", "rationale": "matches"}')])
    runner = EvalRunner(
        _AnsweringPipeline(),
        Judge(judge_provider),
        gold,
        collection="transmissions",
        collections=COLLECTIONS,
    )
    [entry_report] = (await runner.run()).entries
    assert entry_report.verdict == "grounded"
