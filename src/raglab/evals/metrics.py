"""Pure aggregate computation over a completed run's entries.

recall@k is derived from each entry's `recall_hit`; MRR needs the rank of
the first hit within the retrieved order, which the report schema
deliberately doesn't carry (see `runner.py`) — so reciprocal ranks are
passed in separately rather than recomputed from `EntryReport` alone.
"""

from __future__ import annotations

import statistics

from .recall import mrr as compute_mrr
from .recall import recall_at_k as compute_recall_at_k
from .report import Aggregates, EntryReport, TagAggregates

GROUNDEDNESS_VERDICTS = ("grounded", "not_grounded")
REFUSAL_VERDICTS = ("refused_correctly", "refused_incorrectly")


def _rate(hits: int, total: int) -> float | None:
    return (hits / total) if total else None


def _mean(values: list[float]) -> float | None:
    return (sum(values) / len(values)) if values else None


def _citation_stats(entries: list[EntryReport]) -> tuple[float | None, float | None, float | None, int]:
    """(citation_precision, fabrication_rate, mean_coverage, uncited count)."""
    cited_entries = [e for e in entries if e.cited is not None]
    uncited = sum(1 for e in entries if e.cited is None)
    fabrication_rate = _rate(sum(1 for e in cited_entries if e.fabricated), len(cited_entries))
    citation_precision = _mean([e.citation_precision for e in entries if e.citation_precision is not None])
    mean_coverage = _mean([e.coverage for e in entries if e.coverage is not None])
    return citation_precision, fabrication_rate, mean_coverage, uncited


def _tag_aggregate(entries: list[EntryReport]) -> TagAggregates:
    graded = [e for e in entries if e.status == "graded"]
    groundedness_entries = [e for e in graded if e.verdict in GROUNDEDNESS_VERDICTS]
    refusal_entries = [e for e in graded if e.verdict in REFUSAL_VERDICTS]
    recall_hits = [e.recall_hit for e in entries if e.recall_hit is not None]
    citation_precision, fabrication_rate, mean_coverage, uncited = _citation_stats(entries)
    input_tokens = [e.usage.input_tokens for e in entries if e.usage is not None]

    return TagAggregates(
        count=len(entries),
        grounded_rate=_rate(sum(1 for e in groundedness_entries if e.verdict == "grounded"), len(groundedness_entries)),
        refusal_correct_rate=_rate(
            sum(1 for e in refusal_entries if e.verdict == "refused_correctly"), len(refusal_entries)
        ),
        recall_at_k=compute_recall_at_k(recall_hits),
        citation_precision=citation_precision,
        fabrication_rate=fabrication_rate,
        mean_coverage=mean_coverage,
        uncited=uncited,
        mean_input_tokens=_mean(input_tokens) if input_tokens else None,
    )


def _compute_by_tag(entries: list[EntryReport], tags_by_id: dict[str, list[str]]) -> dict[str, TagAggregates]:
    grouped: dict[str, list[EntryReport]] = {}
    for entry in entries:
        for tag in tags_by_id.get(entry.id, []):
            grouped.setdefault(tag, []).append(entry)
    return {tag: _tag_aggregate(tagged_entries) for tag, tagged_entries in sorted(grouped.items())}


def _compute_by_turn_position(
    entries: list[EntryReport], turn_position_by_id: dict[str, str]
) -> dict[str, TagAggregates]:
    grouped: dict[str, list[EntryReport]] = {}
    for entry in entries:
        position = turn_position_by_id.get(entry.id)
        if position is not None:
            grouped.setdefault(position, []).append(entry)
    return {position: _tag_aggregate(es) for position, es in sorted(grouped.items())}


def compute_aggregates(
    entries: list[EntryReport],
    reciprocal_ranks: list[float] | None = None,
    tags_by_id: dict[str, list[str]] | None = None,
    turn_position_by_id: dict[str, str] | None = None,
) -> Aggregates:
    graded = [e for e in entries if e.status == "graded"]
    ungraded = [e for e in entries if e.status == "ungraded"]
    skipped = [e for e in entries if e.status == "skipped"]
    errored = [e for e in entries if e.status == "errored"]

    groundedness_entries = [e for e in graded if e.verdict in GROUNDEDNESS_VERDICTS]
    refusal_entries = [e for e in graded if e.verdict in REFUSAL_VERDICTS]

    grounded_rate = _rate(sum(1 for e in groundedness_entries if e.verdict == "grounded"), len(groundedness_entries))
    refusal_correct_rate = _rate(
        sum(1 for e in refusal_entries if e.verdict == "refused_correctly"), len(refusal_entries)
    )

    recall_hits = [e.recall_hit for e in entries if e.recall_hit is not None]

    input_tokens = sum(e.usage.input_tokens for e in entries if e.usage is not None)
    output_tokens = sum(e.usage.output_tokens for e in entries if e.usage is not None)
    latencies = [e.latency_s for e in entries if e.latency_s is not None]

    citation_precision, fabrication_rate, mean_coverage, uncited = _citation_stats(entries)
    by_tag = _compute_by_tag(entries, tags_by_id) if tags_by_id else {}
    by_turn_position = _compute_by_turn_position(entries, turn_position_by_id) if turn_position_by_id else {}

    return Aggregates(
        grounded_rate=grounded_rate,
        refusal_correct_rate=refusal_correct_rate,
        graded=len(graded),
        ungraded=len(ungraded),
        skipped=len(skipped),
        errored=len(errored),
        recall_at_k=compute_recall_at_k(recall_hits),
        mrr=compute_mrr(reciprocal_ranks or []),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        p50_latency_s=statistics.median(latencies) if latencies else 0.0,
        citation_precision=citation_precision,
        fabrication_rate=fabrication_rate,
        mean_coverage=mean_coverage,
        uncited=uncited,
        by_tag=by_tag,
        by_turn_position=by_turn_position,
    )


def find_disagreements(entries: list[EntryReport]) -> list[EntryReport]:
    """Entries where the deterministic citation check and the LLM judge
    reach opposite conclusions (plan.md): judge says grounded with zero
    citation precision, or not_grounded with perfect citation precision."""
    disagreements = []
    for entry in entries:
        if entry.citation_precision is None or entry.verdict not in GROUNDEDNESS_VERDICTS:
            continue
        if (entry.verdict == "grounded" and entry.citation_precision == 0.0) or (
            entry.verdict == "not_grounded" and entry.citation_precision == 1.0
        ):
            disagreements.append(entry)
    return disagreements
