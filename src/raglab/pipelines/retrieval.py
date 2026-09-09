"""Retrieval pipeline: search the active collection, answer from retrieved chunks only.

`doc_hint` is ignored — retrieval always searches every document in the
active collection, per spec. A gold entry's `doc` becomes ground truth for
scoring, never a filter narrowing the search. Conversation history reaches
the model but never the retriever by default: retrieval runs on the final
turn's raw question alone unless a `QueryRewriter` is configured -- see
pipelines/base.py and retrieval/rewriter.py. Rewriting only changes the
*retrieval query*; the answer call still gets the raw history and the raw
final question, exactly as before.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from ..evals.citations import parse_citations, strip_citations_block
from ..providers.base import LLMProvider, Message, Usage
from ..retrieval.fusion import DEFAULT_RRF_K
from ..retrieval.reranker import Reranker
from ..retrieval.retriever import RetrievalMode, RetrievedChunk, Retriever
from ..retrieval.rewriter import QueryRewriter
from .base import ConversationTurn, PipelineResult, Query, StreamChunk

# The exact opening tag `evals/citations.py`'s CITATION_BLOCK_RE looks for --
# duplicated here (not imported) because streaming needs the bare prefix to
# search a growing buffer for, not the full delimited-block pattern.
CITATION_TAG_START = "<citations"

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


def _tag_prefix_holdback(buffer: str, tag: str) -> int:
    """Length of the longest suffix of `buffer` that is itself a proper
    prefix of `tag` -- i.e. how many trailing characters might still turn
    into `tag` once more text arrives, and so must not be emitted yet."""
    for length in range(min(len(buffer), len(tag) - 1), 0, -1):
        if tag.startswith(buffer[-length:]):
            return length
    return 0


class RetrievalPipeline:
    name = "retrieval"

    def __init__(
        self,
        provider: LLMProvider,
        retriever: Retriever,
        *,
        top_k: int = DEFAULT_TOP_K,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        mode: RetrievalMode = "dense",
        candidate_k: int | None = None,
        rrf_k: int = DEFAULT_RRF_K,
        reranker: Reranker | None = None,
        rewriter: QueryRewriter | None = None,
    ):
        self.provider = provider
        self.retriever = retriever
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.mode = mode
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k
        self.reranker = reranker
        self.rewriter = rewriter

    def _build_messages(
        self, history: list[ConversationTurn], question: str, chunks: list[RetrievedChunk]
    ) -> list[Message]:
        excerpts = "\n\n".join(f"[{c.chunk_id}] ({c.doc})\n{c.text}" for c in chunks)
        messages = [Message(role="system", content=SYSTEM_PROMPT)]
        for turn in history:
            messages.append(Message(role="user", content=turn.question))
            messages.append(Message(role="assistant", content=turn.answer))
        messages.append(Message(role="user", content=f"EXCERPTS:\n{excerpts}\n\nQUESTION:\n{question}"))
        return messages

    async def _relevant_chunks(self, query: Query) -> tuple[list[RetrievedChunk], str | None]:
        rewritten_query = None
        if self.rewriter is not None:
            rewritten_query = await self.rewriter.rewrite(query.history, query.question)
        retrieval_query = rewritten_query if rewritten_query is not None else query.question

        search_kwargs = dict(
            k=self.top_k, collection=query.collection, candidate_k=self.candidate_k, reranker=self.reranker
        )
        if self.mode == "hybrid":
            chunks = self.retriever.search(retrieval_query, mode="hybrid", rrf_k=self.rrf_k, **search_kwargs)
        else:
            chunks = self.retriever.search(retrieval_query, **search_kwargs)

        # RRF's fused score and a cross-encoder's rerank score each live on
        # their own scale, not cosine similarity -- score_threshold only
        # means anything for plain dense search. Hybrid fusion and
        # reranking both already discard non-matches on their own terms, so
        # an empty `chunks` list is itself the "nothing relevant" signal.
        rescored = self.mode == "hybrid" or self.reranker is not None
        relevant = chunks if rescored else [c for c in chunks if c.score >= self.score_threshold]
        return relevant, rewritten_query

    @staticmethod
    def _no_relevant_chunks_result(rewritten_query: str | None) -> PipelineResult:
        return PipelineResult(
            answer=NO_RELEVANT_CHUNKS_ANSWER,
            stop_reason=NO_RELEVANT_CHUNKS_STOP_REASON,
            usage=Usage(input_tokens=0, output_tokens=0),
            latency_s=0.0,
            retrieved=[],
            retrieved_scores=[],
            rewritten_query=rewritten_query,
        )

    async def answer(self, query: Query) -> PipelineResult:
        relevant, rewritten_query = await self._relevant_chunks(query)
        if not relevant:
            return self._no_relevant_chunks_result(rewritten_query)

        # The answer call always gets the raw history and the raw final
        # question, unchanged by rewriting -- only the retrieval query above
        # is affected. See module docstring.
        messages = self._build_messages(query.history, query.question, relevant)
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
            retrieved_scores=[c.score for c in relevant],
            cited=cited,
            rewritten_query=rewritten_query,
        )

    async def answer_stream(self, query: Query) -> AsyncIterator[StreamChunk]:
        """Same answer as `answer()`, delivered incrementally. A *new*
        method rather than a change to `answer()` -- the eval harness calls
        `answer()` and must keep producing identical results; a test pins
        the two to the same output for the same input (plan.md).

        The model's raw text stream still contains the trailing
        `<citations>` block -- `strip_citations_block` only works on
        complete text, so the cut has to happen here, incrementally, by
        holding back any buffered suffix that could be the start of the
        tag until either it resolves into the tag (stop emitting) or more
        text arrives that rules it out (flush and continue). Everything
        after the tag starts is drained silently, since it belongs to the
        citations block, not the prose.
        """
        relevant, rewritten_query = await self._relevant_chunks(query)
        if not relevant:
            result = self._no_relevant_chunks_result(rewritten_query)
            yield StreamChunk(text=result.answer)
            yield StreamChunk(done=True, result=result)
            return

        messages = self._build_messages(query.history, query.question, relevant)
        await self.provider.check_over_context(messages)

        start = time.perf_counter()
        full_text = ""
        buffer = ""
        citations_started = False

        async for piece in self.provider.stream(messages):
            if piece.done:
                continue
            full_text += piece.text
            if citations_started:
                continue

            buffer += piece.text
            tag_index = buffer.find(CITATION_TAG_START)
            if tag_index != -1:
                # rstrip so the newline the system prompt puts before the
                # block never reaches the client -- matches
                # strip_citations_block's final .strip() on the same text.
                prose = buffer[:tag_index].rstrip()
                if prose:
                    yield StreamChunk(text=prose)
                citations_started = True
                buffer = ""
                continue

            # Hold back a trailing whitespace run too, not just a partial
            # tag prefix -- otherwise a newline gets flushed as prose one
            # chunk before the tag that follows it is even seen.
            trailing_ws = len(buffer) - len(buffer.rstrip())
            holdback = max(_tag_prefix_holdback(buffer, CITATION_TAG_START), trailing_ws)
            if holdback < len(buffer):
                yield StreamChunk(text=buffer[: len(buffer) - holdback])
                buffer = buffer[len(buffer) - holdback :]

        if not citations_started and buffer:
            yield StreamChunk(text=buffer)

        latency_s = time.perf_counter() - start
        cited = parse_citations(full_text)
        answer_text = strip_citations_block(full_text) if cited is not None else full_text

        result = PipelineResult(
            answer=answer_text,
            # Chunk carries no stop_reason/usage -- streaming's cost is
            # deliberately unmeasured this phase (spec: "Nothing else is
            # recorded. No latency, no token accounting").
            stop_reason="end_turn",
            usage=Usage(input_tokens=0, output_tokens=0),
            latency_s=latency_s,
            retrieved=[c.chunk_id for c in relevant],
            retrieved_scores=[c.score for c in relevant],
            cited=cited,
            rewritten_query=rewritten_query,
        )
        yield StreamChunk(done=True, result=result)
