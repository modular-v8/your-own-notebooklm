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
from .report import Aggregates, EntryReport

GROUNDEDNESS_VERDICTS = ("grounded", "not_grounded")
REFUSAL_VERDICTS = ("refused_correctly", "refused_incorrectly")


def compute_aggregates(entries: list[EntryReport], reciprocal_ranks: list[float] | None = None) -> Aggregates:
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

    recall_hits = [e.recall_hit for e in entries if e.recall_hit is not None]

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
        recall_at_k=compute_recall_at_k(recall_hits),
        mrr=compute_mrr(reciprocal_ranks or []),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        p50_latency_s=statistics.median(latencies) if latencies else 0.0,
    )
