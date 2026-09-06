"""Phase 0 baseline: the entire document in context, answer from it, cite.

A document that doesn't fit is refused, never truncated — a truncated
document would score low for a reason unrelated to retrieval, poisoning
every later comparison drawn against this baseline. Behavior is unchanged
from Phase 0; only the plumbing moved to resolve `doc_hint` itself.
"""

from __future__ import annotations

import time

from ..providers.base import LLMProvider, Message
from .base import ConversationTurn, PipelineResult, PipelineSkip, Query

SYSTEM_PROMPT = (
    "You answer questions using ONLY the document provided below. "
    "If the document does not contain the answer, say plainly that you "
    "cannot answer from the provided document — do not guess or use "
    "outside knowledge. Cite the part of the document your answer relies on."
)

CROSS_DOCUMENT_SKIP_REASON = (
    "cross-document entry: the whole-document baseline puts exactly one document "
    "in context and structurally cannot answer a question whose gold spans live "
    "in more than one document"
)


class WholeDocPipeline:
    name = "whole_doc"

    def __init__(self, provider: LLMProvider, documents: dict[str, str]):
        self.provider = provider
        self.documents = documents

    def _build_messages(
        self, history: list[ConversationTurn], question: str, doc_text: str
    ) -> list[Message]:
        messages = [Message(role="system", content=SYSTEM_PROMPT)]
        for turn in history:
            messages.append(Message(role="user", content=turn.question))
            messages.append(Message(role="assistant", content=turn.answer))
        messages.append(Message(role="user", content=f"DOCUMENT:\n{doc_text}\n\nQUESTION:\n{question}"))
        return messages

    async def answer(self, query: Query) -> PipelineResult:
        if query.cross_document:
            raise PipelineSkip(CROSS_DOCUMENT_SKIP_REASON)
        doc_text = self.documents[query.doc_hint]
        messages = self._build_messages(query.history, query.question, doc_text)
        await self.provider.check_over_context(messages)

        start = time.perf_counter()
        completion = await self.provider.complete(messages)
        latency_s = time.perf_counter() - start

        return PipelineResult(
            answer=completion.text,
            stop_reason=completion.stop_reason,
            usage=completion.usage,
            latency_s=latency_s,
            request_params=completion.request_params,
            retrieved=None,
        )
