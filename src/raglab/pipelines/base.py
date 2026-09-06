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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..providers.base import Usage


@dataclass(frozen=True)
class Query:
    question: str
    doc_hint: str
    cross_document: bool = False


@dataclass(frozen=True)
class PipelineResult:
    answer: str
    stop_reason: str
    usage: Usage
    latency_s: float
    request_params: dict[str, Any] = field(default_factory=dict)
    retrieved: list[str] | None = None
    # The chunk ids the model claimed to have relied on, parsed from its
    # own <citations> block. None means no such block was found (uncited),
    # distinct from an empty list (a block naming nothing). Only pipelines
    # that instruct the model to cite (retrieval.py) ever populate this.
    cited: list[str] | None = None


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
