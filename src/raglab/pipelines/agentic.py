"""Agentic retrieval: the model calls a `search` tool itself, deciding when
and how many times to search, instead of retrieving once up front before
any model call (specs/4-retrieval-optimization Milestone 7 -- the control-
flow comparison this project opened with: does letting the model decide
when and what to search beat retrieving once up front?).

The tool-call loop itself lives inside the provider, not here -- T2.7's
probe proved `AgentSDKProvider` already runs one internal request/execute/
respond loop per `complete()` call, accumulating every `ToolCallRecord` onto
one final `Completion` (providers/base.py). This pipeline's job is just to
define the `search` tool and enforce `max_calls` as a hard ceiling from
inside the tool's own handler -- nothing outside the provider's internal
loop can interrupt it mid-flight, so the cap has to live where the calls
actually happen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..evals.citations import parse_citations, strip_citations_block
from ..providers.base import LLMProvider, Message, ToolSpec
from ..retrieval.retriever import RetrievedChunk, Retriever
from .base import ConversationTurn, PipelineResult, Query

DEFAULT_TOP_K = 5
DEFAULT_MAX_CALLS = 5

SEARCH_TOOL_NAME = "search"

CALL_LIMIT_MESSAGE_TEMPLATE = (
    "Search budget exhausted ({max_calls} calls used) -- no further searches "
    "allowed. Answer using only what you have already retrieved, or say you "
    "cannot answer from the material found so far."
)

SYSTEM_PROMPT = (
    "You answer questions about a document corpus. You do not have the "
    "content in front of you -- use the `search` tool to find relevant "
    "excerpts before answering, and you may search more than once if the "
    "first results don't fully answer the question. Once you have enough "
    "information (or your search budget runs out), answer using ONLY the "
    "excerpts you retrieved -- do not guess or use outside knowledge. "
    "After your answer, on its own line, list the chunk ids of every excerpt "
    "you actually relied on inside a <citations> block, comma-separated -- "
    "for example <citations>fb_rules.pdf:0042, fb_rules.pdf:0043</citations>. "
    "If you relied on none (for example, because you are declining to "
    "answer), write <citations></citations>."
)

SEARCH_TOOL_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string", "description": "The search query."}},
    "required": ["query"],
}


@dataclass
class _SearchState:
    """Mutable, one per `answer()` call -- captured by the tool handler's
    closure, since the handler is the only thing that runs once per actual
    search rather than once per pipeline call."""

    call_count: int = 0
    capped: bool = False
    seen_chunks: dict[str, RetrievedChunk] = field(default_factory=dict)


class AgenticPipeline:
    name = "agentic"

    def __init__(
        self,
        provider: LLMProvider,
        retriever: Retriever,
        *,
        top_k: int = DEFAULT_TOP_K,
        max_calls: int = DEFAULT_MAX_CALLS,
    ):
        self.provider = provider
        self.retriever = retriever
        self.top_k = top_k
        self.max_calls = max_calls

    def _build_search_tool(self, state: _SearchState, collection: str | None) -> ToolSpec:
        async def handler(args: dict) -> dict:
            if state.call_count >= self.max_calls:
                state.capped = True
                return {"error": CALL_LIMIT_MESSAGE_TEMPLATE.format(max_calls=self.max_calls)}

            state.call_count += 1
            query = str(args.get("query", ""))
            chunks = self.retriever.search(query, k=self.top_k, collection=collection)
            for chunk in chunks:
                state.seen_chunks.setdefault(chunk.chunk_id, chunk)

            return {"results": [{"chunk_id": c.chunk_id, "doc": c.doc, "text": c.text} for c in chunks]}

        return ToolSpec(
            name=SEARCH_TOOL_NAME,
            description=(
                "Search the document corpus for relevant excerpts. Call again "
                "with a different, more specific query if the results don't "
                "fully answer the question."
            ),
            input_schema=SEARCH_TOOL_SCHEMA,
            handler=handler,
        )

    def _build_messages(self, history: list[ConversationTurn], question: str) -> list[Message]:
        messages = [Message(role="system", content=SYSTEM_PROMPT)]
        for turn in history:
            messages.append(Message(role="user", content=turn.question))
            messages.append(Message(role="assistant", content=turn.answer))
        messages.append(Message(role="user", content=question))
        return messages

    async def answer(self, query: Query) -> PipelineResult:
        state = _SearchState()
        tool = self._build_search_tool(state, query.collection)
        messages = self._build_messages(query.history, query.question)

        await self.provider.check_over_context(messages)

        start = time.perf_counter()
        completion = await self.provider.complete(messages, tools=[tool])
        latency_s = time.perf_counter() - start

        cited = parse_citations(completion.text)
        answer_text = strip_citations_block(completion.text) if cited is not None else completion.text

        return PipelineResult(
            answer=answer_text,
            stop_reason=completion.stop_reason,
            usage=completion.usage,
            latency_s=latency_s,
            request_params=completion.request_params,
            retrieved=list(state.seen_chunks.keys()),
            cited=cited,
            retrieval_calls=state.call_count,
            capped=state.capped,
        )
