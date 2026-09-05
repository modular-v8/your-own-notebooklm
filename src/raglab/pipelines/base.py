"""Pipeline protocol: the one seam every retrieval phase implements identically.

Phase 1 revises `answer()` to take a `Query` instead of `(question, doc_text)`
so a pipeline can resolve its own context — a retrieval pipeline needs an
index and may draw from several documents, which the Phase 0 signature
couldn't express. `doc_hint` is used two ways downstream: handing the
whole-doc baseline its document, and scoring recall against the right gold
spans. It is never a search filter — retrieval always sees the whole corpus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..providers.base import Usage


@dataclass(frozen=True)
class Query:
    question: str
    doc_hint: str


@dataclass(frozen=True)
class PipelineResult:
    answer: str
    stop_reason: str
    usage: Usage
    latency_s: float
    request_params: dict[str, Any] = field(default_factory=dict)
    retrieved: list[str] | None = None


@runtime_checkable
class Pipeline(Protocol):
    name: str

    async def answer(self, query: Query) -> PipelineResult: ...
