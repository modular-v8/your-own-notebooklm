"""Pipeline protocol: the one seam every retrieval phase implements identically.

The eval runner, judge, and report schema are written once against
`Pipeline.answer()`. Phase 1+ add new implementations here without touching
anything downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..providers.base import Usage


@dataclass(frozen=True)
class PipelineResult:
    answer: str
    stop_reason: str
    usage: Usage
    latency_s: float
    request_params: dict[str, Any]


@runtime_checkable
class Pipeline(Protocol):
    name: str

    async def answer(self, question: str, doc_text: str) -> PipelineResult: ...
