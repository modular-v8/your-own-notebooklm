"""Async orchestration: run every gold-set entry against a pipeline and judge.

Concurrency-bounded by a semaphore; result order matches gold-set order
regardless of completion order, since asyncio.gather preserves input order.
"""

from __future__ import annotations

import asyncio

from ..corpus import Document
from ..pipelines.base import Pipeline
from ..providers.base import OverContextError
from .goldset import NOT_IN_DOCUMENT_TAG, GoldEntry, GoldSet
from .judge import Judge
from .report import EntryReport, UsageReport

SAFETY_REFUSAL_STOP_REASON = "refusal"
DEFAULT_CONCURRENCY = 5


async def _run_entry(entry: GoldEntry, doc: Document, pipeline: Pipeline, judge: Judge) -> EntryReport:
    try:
        result = await pipeline.answer(entry.question, doc.text)
    except OverContextError as exc:
        return EntryReport(id=entry.id, status="skipped", error=str(exc))
    except Exception as exc:  # provider/transport failure: recorded, not raised, so one bad entry doesn't kill the run
        return EntryReport(id=entry.id, status="errored", error=str(exc))

    usage = UsageReport(input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens)

    # A safety refusal and a content-grounded "not in this document" refusal
    # look identical in the text but are different events — conflating them
    # would corrupt the not-answerable-from-document metric.
    if result.stop_reason == SAFETY_REFUSAL_STOP_REASON:
        return EntryReport(
            id=entry.id,
            status="ungraded",
            answer=result.answer,
            stop_reason=result.stop_reason,
            usage=usage,
            latency_s=result.latency_s,
            rationale="safety refusal, not a content judgment",
        )

    if NOT_IN_DOCUMENT_TAG in entry.tags:
        judge_result = await judge.score_refusal(entry.question, result.answer)
    else:
        judge_result = await judge.score_groundedness(
            entry.question, entry.expected_answer, entry.answer_location, result.answer
        )

    return EntryReport(
        id=entry.id,
        status="graded" if judge_result.verdict is not None else "ungraded",
        answer=result.answer,
        verdict=judge_result.verdict,
        rationale=judge_result.rationale,
        stop_reason=result.stop_reason,
        usage=usage,
        latency_s=result.latency_s,
    )


class EvalRunner:
    def __init__(
        self,
        pipeline: Pipeline,
        judge: Judge,
        gold: GoldSet,
        documents: dict[str, Document],
        concurrency: int = DEFAULT_CONCURRENCY,
    ):
        self.pipeline = pipeline
        self.judge = judge
        self.gold = gold
        self.documents = documents
        self.concurrency = concurrency

    async def run(self) -> list[EntryReport]:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def bound(entry: GoldEntry) -> EntryReport:
            async with semaphore:
                return await _run_entry(entry, self.documents[entry.doc], self.pipeline, self.judge)

        return await asyncio.gather(*(bound(entry) for entry in self.gold.entries))
