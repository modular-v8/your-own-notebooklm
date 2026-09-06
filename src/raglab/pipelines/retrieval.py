"""Retrieval pipeline: search the whole corpus, answer from retrieved chunks only.

`doc_hint` is ignored — retrieval always searches every indexed document,
per spec. A gold entry's `doc` becomes ground truth for scoring, never a
filter narrowing the search.
"""

from __future__ import annotations

import time

from ..evals.citations import parse_citations, strip_citations_block
from ..providers.base import LLMProvider, Message, Usage
from ..retrieval.retriever import RetrievedChunk, Retriever
from .base import PipelineResult, Query

DEFAULT_TOP_K = 5
DEFAULT_SCORE_THRESHOLD = 0.35

SYSTEM_PROMPT = (
    "You answer questions using ONLY the retrieved excerpts provided below. "
    "If the excerpts do not contain the answer, say plainly that you cannot "
    "answer from the provided material — do not guess or use outside "
    "knowledge. "
    "After your answer, on its own line, list the chunk ids of every excerpt "
    "you actually relied on inside a <citations> block, comma-separated — "
    "for example <citations>fb_rules.pdf:0042, fb_rules.pdf:0043</citations>. "
    "If you relied on none (for example, because you are declining to "
    "answer), write <citations></citations>. Use exactly the chunk ids shown "
    "in brackets before each excerpt below; do not invent ids."
)

# A refusal produced here costs no model call — there's nothing relevant to
# reason over, so asking the model to say so would just spend tokens to
# reach the same answer.
NO_RELEVANT_CHUNKS_STOP_REASON = "no_relevant_chunks"
NO_RELEVANT_CHUNKS_ANSWER = (
    "I cannot answer this from the retrieved material — no excerpt scored above the relevance threshold."
)


class RetrievalPipeline:
    name = "retrieval"

    def __init__(
        self,
        provider: LLMProvider,
        retriever: Retriever,
        *,
        top_k: int = DEFAULT_TOP_K,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    ):
        self.provider = provider
        self.retriever = retriever
        self.top_k = top_k
        self.score_threshold = score_threshold

    def _build_messages(self, question: str, chunks: list[RetrievedChunk]) -> list[Message]:
        excerpts = "\n\n".join(f"[{c.chunk_id}] ({c.doc})\n{c.text}" for c in chunks)
        return [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=f"EXCERPTS:\n{excerpts}\n\nQUESTION:\n{question}"),
        ]

    async def answer(self, query: Query) -> PipelineResult:
        chunks = self.retriever.search(query.question, k=self.top_k)
        relevant = [c for c in chunks if c.score >= self.score_threshold]

        if not relevant:
            return PipelineResult(
                answer=NO_RELEVANT_CHUNKS_ANSWER,
                stop_reason=NO_RELEVANT_CHUNKS_STOP_REASON,
                usage=Usage(input_tokens=0, output_tokens=0),
                latency_s=0.0,
                retrieved=[],
            )

        messages = self._build_messages(query.question, relevant)
        await self.provider.check_over_context(messages)

        start = time.perf_counter()
        completion = await self.provider.complete(messages)
        latency_s = time.perf_counter() - start

        cited = parse_citations(completion.text)
        answer_text = strip_citations_block(completion.text) if cited is not None else completion.text

        return PipelineResult(
            answer=answer_text,
            stop_reason=completion.stop_reason,
            usage=completion.usage,
            latency_s=latency_s,
            request_params=completion.request_params,
            retrieved=[c.chunk_id for c in relevant],
            cited=cited,
        )
