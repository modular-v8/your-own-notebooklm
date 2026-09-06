"""Async orchestration: run every gold-set entry against a pipeline and judge.

Concurrency-bounded by a semaphore; result order matches gold-set order
regardless of completion order, since asyncio.gather preserves input order.

Recall/MRR/coverage/citation-precision scoring all need the char span of
each retrieved chunk, which the report schema deliberately doesn't carry
(only chunk ids, per spec) — so `gold_spans`/`chunk_spans` are passed in
from the caller (built once from the index and the location resolver)
rather than looked up per entry here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..pipelines.base import Pipeline, PipelineSkip, Query
from ..providers.base import OverContextError
from .citations import CitationResult, score_citations
from .coverage import score_coverage
from .goldset import NOT_IN_DOCUMENT_TAG, GoldEntry, GoldSet
from .judge import Judge
from .locations import CharSpan, GoldSpan
from .recall import score_retrieval
from .report import EntryReport, UsageReport

SAFETY_REFUSAL_STOP_REASON = "refusal"
DEFAULT_CONCURRENCY = 5


def _build_query(entry: GoldEntry, primary_doc: str | None) -> Query:
    docs = entry.docs
    if len(docs) > 1:
        # doc_hint is informational only here; the whole-doc pipeline must
        # skip before ever reading it, and retrieval ignores it regardless.
        return Query(question=entry.question, doc_hint=docs[0], cross_document=True)
    doc_hint = docs[0] if docs else (primary_doc or "")
    return Query(question=entry.question, doc_hint=doc_hint)


def _score_recall(
    entry: GoldEntry,
    retrieved: list[str] | None,
    gold_spans: dict[str, list[GoldSpan]],
    chunk_spans: dict[str, CharSpan],
) -> tuple[bool | None, float | None]:
    if retrieved is None:
        return None, None  # pipeline doesn't retrieve (whole_doc baseline)

    entry_spans = gold_spans.get(entry.id)
    if not entry_spans:
        return None, None  # not-in-document entry: no gold span to score against

    ranked = [(chunk_id, chunk_spans[chunk_id]) for chunk_id in retrieved if chunk_id in chunk_spans]
    score = score_retrieval(entry_spans, ranked)
    reciprocal_rank = 1.0 / score.rank_of_first_hit if score.rank_of_first_hit else 0.0
    return score.recall_hit, reciprocal_rank


def _score_citations_and_coverage(
    entry: GoldEntry,
    cited: list[str] | None,
    retrieved: list[str] | None,
    gold_spans: dict[str, list[GoldSpan]],
    chunk_spans: dict[str, CharSpan],
) -> tuple[CitationResult, float | None]:
    entry_spans = gold_spans.get(entry.id, [])
    citation_result = score_citations(cited, retrieved or [], entry_spans, chunk_spans)

    coverage = None
    if retrieved is not None:
        ranked = [(chunk_id, chunk_spans[chunk_id]) for chunk_id in retrieved if chunk_id in chunk_spans]
        coverage = score_coverage(entry_spans, ranked)
    return citation_result, coverage


async def _run_entry(
    entry: GoldEntry,
    pipeline: Pipeline,
    judge: Judge,
    gold_spans: dict[str, list[GoldSpan]],
    chunk_spans: dict[str, CharSpan],
    primary_doc: str | None,
) -> tuple[EntryReport, float | None]:
    query = _build_query(entry, primary_doc)
    try:
        result = await pipeline.answer(query)
    except OverContextError as exc:
        return EntryReport(id=entry.id, status="skipped", error=str(exc)), None
    except PipelineSkip as exc:
        return EntryReport(id=entry.id, status="skipped", error=exc.reason), None
    except Exception as exc:  # provider/transport failure: recorded, not raised, so one bad entry doesn't kill the run
        return EntryReport(id=entry.id, status="errored", error=str(exc)), None

    usage = UsageReport(input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens)
    recall_hit, reciprocal_rank = _score_recall(entry, result.retrieved, gold_spans, chunk_spans)
    citation_result, coverage = _score_citations_and_coverage(
        entry, result.cited, result.retrieved, gold_spans, chunk_spans
    )

    # A safety refusal and a content-grounded "not in this document" refusal
    # look identical in the text but are different events — conflating them
    # would corrupt the not-answerable-from-document metric.
    if result.stop_reason == SAFETY_REFUSAL_STOP_REASON:
        return (
            EntryReport(
                id=entry.id,
                status="ungraded",
                answer=result.answer,
                stop_reason=result.stop_reason,
                retrieved=result.retrieved,
                recall_hit=recall_hit,
                usage=usage,
                latency_s=result.latency_s,
                rationale="safety refusal, not a content judgment",
                cited=citation_result.cited,
                fabricated=citation_result.fabricated,
                citation_precision=citation_result.citation_precision,
                coverage=coverage,
            ),
            reciprocal_rank,
        )

    if NOT_IN_DOCUMENT_TAG in entry.tags:
        judge_result = await judge.score_refusal(entry.question, result.answer)
    else:
        judge_result = await judge.score_groundedness(
            entry.question, entry.expected_answer, entry.sources, result.answer
        )

    return (
        EntryReport(
            id=entry.id,
            status="graded" if judge_result.verdict is not None else "ungraded",
            answer=result.answer,
            verdict=judge_result.verdict,
            rationale=judge_result.rationale,
            stop_reason=result.stop_reason,
            retrieved=result.retrieved,
            recall_hit=recall_hit,
            usage=usage,
            latency_s=result.latency_s,
            cited=citation_result.cited,
            fabricated=citation_result.fabricated,
            citation_precision=citation_result.citation_precision,
            coverage=coverage,
        ),
        reciprocal_rank,
    )


@dataclass(frozen=True)
class RunResult:
    entries: list[EntryReport]
    reciprocal_ranks: list[float] = field(default_factory=list)


class EvalRunner:
    def __init__(
        self,
        pipeline: Pipeline,
        judge: Judge,
        gold: GoldSet,
        concurrency: int = DEFAULT_CONCURRENCY,
        gold_spans: dict[str, list[GoldSpan]] | None = None,
        chunk_spans: dict[str, CharSpan] | None = None,
    ):
        self.pipeline = pipeline
        self.judge = judge
        self.gold = gold
        self.concurrency = concurrency
        self.gold_spans = gold_spans or {}
        self.chunk_spans = chunk_spans or {}

    async def run(self) -> RunResult:
        semaphore = asyncio.Semaphore(self.concurrency)
        primary_doc = self.gold.primary_doc

        async def bound(entry: GoldEntry) -> tuple[EntryReport, float | None]:
            async with semaphore:
                return await _run_entry(
                    entry, self.pipeline, self.judge, self.gold_spans, self.chunk_spans, primary_doc
                )

        results = await asyncio.gather(*(bound(entry) for entry in self.gold.entries))
        entries = [entry_report for entry_report, _ in results]
        reciprocal_ranks = [rank for _, rank in results if rank is not None]
        return RunResult(entries=entries, reciprocal_ranks=reciprocal_ranks)
