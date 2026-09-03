"""Pure aggregate computation over a completed run's entries.

Retrieval metrics (recall@k, mrr) are stubbed null here; Phase 1 populates
them once retrieval exists to measure.
"""

from __future__ import annotations

import statistics

from .report import Aggregates, EntryReport

GROUNDEDNESS_VERDICTS = ("grounded", "not_grounded")
REFUSAL_VERDICTS = ("refused_correctly", "refused_incorrectly")


def compute_aggregates(entries: list[EntryReport]) -> Aggregates:
    graded = [e for e in entries if e.status == "graded"]
    ungraded = [e for e in entries if e.status == "ungraded"]
    skipped = [e for e in entries if e.status == "skipped"]
    errored = [e for e in entries if e.status == "errored"]

    groundedness_entries = [e for e in graded if e.verdict in GROUNDEDNESS_VERDICTS]
    refusal_entries = [e for e in graded if e.verdict in REFUSAL_VERDICTS]

    grounded_rate = (
        sum(1 for e in groundedness_entries if e.verdict == "grounded") / len(groundedness_entries)
        if groundedness_entries
        else None
    )
    refusal_correct_rate = (
        sum(1 for e in refusal_entries if e.verdict == "refused_correctly") / len(refusal_entries)
        if refusal_entries
        else None
    )

    input_tokens = sum(e.usage.input_tokens for e in entries if e.usage is not None)
    output_tokens = sum(e.usage.output_tokens for e in entries if e.usage is not None)
    latencies = [e.latency_s for e in entries if e.latency_s is not None]

    return Aggregates(
        grounded_rate=grounded_rate,
        refusal_correct_rate=refusal_correct_rate,
        graded=len(graded),
        ungraded=len(ungraded),
        skipped=len(skipped),
        errored=len(errored),
        recall_at_k=None,
        mrr=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        p50_latency_s=statistics.median(latencies) if latencies else 0.0,
    )
