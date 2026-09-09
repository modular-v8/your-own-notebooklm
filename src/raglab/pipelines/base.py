"""Pipeline protocol: the one seam every retrieval phase implements identically.

Phase 1 revises `answer()` to take a `Query` instead of `(question, doc_text)`
so a pipeline can resolve its own context — a retrieval pipeline needs an
index and may draw from several documents, which the Phase 0 signature
couldn't express. `doc_hint` is used two ways downstream: handing the
whole-doc baseline its document, and scoring recall against the right gold
spans. It is never a search filter — retrieval always sees the whole corpus.

Phase 2 adds `cross_document`: a gold entry whose sources span more than
one document has no single `doc_hint` a whole-document baseline could use,
and structurally cannot be answered by one — `PipelineSkip` is how a
pipeline declines before making any model call, distinct from
`OverContextError` (document too big) even though the runner records both
as `status="skipped"`.

Phase 3 adds `history` and `collection`. The asymmetry between them is the
whole measurement this phase exists to produce: `collection` scopes
retrieval, but `history` never reaches it — a pipeline hands prior turns to
the model as conversation context while retrieving with the final turn's
raw question alone. Wiring history into retrieval would erase the
follow-up deficit Phase 4 needs to close (see specs/3-collections/plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..providers.base import Usage


@dataclass(frozen=True)
class ConversationTurn:
    """A prior turn's scripted question and answer, decoupled from the
    gold-set schema so a pipeline never has to import evals.goldset."""

    question: str
    answer: str


@dataclass(frozen=True)
class Query:
    question: str
    doc_hint: str
    cross_document: bool = False
    history: list[ConversationTurn] = field(default_factory=list)
    collection: str | None = None


@dataclass(frozen=True)
class PipelineResult:
    answer: str
    stop_reason: str
    usage: Usage
    latency_s: float
    request_params: dict[str, Any] = field(default_factory=dict)
    retrieved: list[str] | None = None
    # Same order and length as `retrieved`, when populated -- lets an
    # offline signal study recompute top1/margin/spread without re-running
    # the retriever (evals.report.EntryReport.retrieved_scores).
    retrieved_scores: list[float] | None = None
    # The chunk ids the model claimed to have relied on, parsed from its
    # own <citations> block. None means no such block was found (uncited),
    # distinct from an empty list (a block naming nothing). Only pipelines
    # that instruct the model to cite (retrieval.py) ever populate this.
    cited: list[str] | None = None
    # Set only when query rewriting actually fired (non-empty history and a
    # rewriter configured) -- None means "not attempted", not "no change",
    # so a report entry can distinguish the two without re-running anything.
    rewritten_query: str | None = None
    # Only AgenticPipeline populates these: how many times the model called
    # the search tool, and whether it hit the configured ceiling (spec:
    # "record the entry as capped, and continue the run" -- capped is a
    # fact about the entry, not a different status; it can still be graded
    # normally on whatever it managed to retrieve before the ceiling hit).
    retrieval_calls: int | None = None
    capped: bool = False
    # Only set when pruning is enabled: how many accumulated chunks were
    # dropped to keep the top-N by score (0 means pruning ran but had
    # nothing to discard). None means pruning wasn't configured at all.
    pruned_discarded: int | None = None


@dataclass(frozen=True)
class StreamChunk:
    """One increment of `RetrievalPipeline.answer_stream()`. `text` is prose
    only -- the `<citations>` block is never emitted this way. `result`
    carries the same `PipelineResult` `answer()` would have returned for an
    identical call, populated only on the terminal chunk (`done=True`) so a
    caller can persist it without re-deriving citations from raw text."""

    text: str = ""
    done: bool = False
    result: PipelineResult | None = None


class PipelineSkip(Exception):
    """Raised by a pipeline that structurally cannot answer a query — e.g.
    a whole-document baseline given a cross-document entry. The runner
    records this as a skipped entry with `reason` as the error, and never
    attempts an answer."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@runtime_checkable
class Pipeline(Protocol):
    name: str

    async def answer(self, query: Query) -> PipelineResult: ...
