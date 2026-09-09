"""Candidate escalation signals computed from one dense retrieval.

Retrieval is deterministic and entirely local (specs/5-adaptive-retrieval
plan.md, Approach Summary), so every signal here is recomputed for free from
a `Retriever.search()` result -- no model call, no new index. Scores are
assumed already sorted descending, which is what `Retriever.search()`
returns.
"""

from __future__ import annotations

from dataclasses import dataclass

from .retriever import RetrievedChunk


@dataclass(frozen=True)
class Signals:
    top1: float
    margin: float
    spread: float
    count_above: int
    doc_agreement: int


def compute_signals(chunks: list[RetrievedChunk], threshold: float) -> Signals:
    if not chunks:
        return Signals(top1=0.0, margin=0.0, spread=0.0, count_above=0, doc_agreement=0)

    scores = [c.score for c in chunks]
    top1 = scores[0]
    # A lone match has no second score to compare against -- treated as the
    # maximal margin (an unrivaled top-1 is the least ambiguous case there
    # is), not an undefined one.
    margin = top1 - scores[1] if len(scores) > 1 else top1
    spread = top1 - scores[-1]
    count_above = sum(1 for score in scores if score >= threshold)
    doc_agreement = len({c.doc for c in chunks})

    return Signals(top1=top1, margin=margin, spread=spread, count_above=count_above, doc_agreement=doc_agreement)
