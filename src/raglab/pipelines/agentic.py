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

# specs/5-adaptive-retrieval T6.1: opt-in, not the default -- T6.2 measured
# this on the 20-entry hard subset (citation_precision 68.0%->65.6%, an even
# 4-win/4-loss split per-entry) and found no net benefit, so `agentic-v1`
# itself must keep Phase 4's exact prompt for the comparison to stay valid.
# Kept available under `tight_citations=True` for the record, the same way
# rejected Phase 4 techniques stayed in experiments.toml as named variants.
# Wording and position (inserted before the empty-citations fallback, not
# appended) match exactly what T6.2 measured -- reordering it would make
# this a different, unmeasured prompt.
SYSTEM_PROMPT_TIGHT_CITATIONS = (
    "You answer questions about a document corpus. You do not have the "
    "content in front of you -- use the `search` tool to find relevant "
    "excerpts before answering, and you may search more than once if the "
    "first results don't fully answer the question. Once you have enough "
    "information (or your search budget runs out), answer using ONLY the "
    "excerpts you retrieved -- do not guess or use outside knowledge. "
    "After your answer, on its own line, list the chunk ids of every excerpt "
    "you actually relied on inside a <citations> block, comma-separated -- "
    "for example <citations>fb_rules.pdf:0042, fb_rules.pdf:0043</citations>. "
    "Cite tightly: name a chunk only if a specific claim in your answer "
    "depends on it, not every excerpt you searched or read along the way. "
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
        prune_top_n: int | None = None,
        tight_citations: bool = False,
    ):
        self.provider = provider
        self.retriever = retriever
        self.top_k = top_k
        self.max_calls = max_calls
        self.prune_top_n = prune_top_n
        self.tight_citations = tight_citations

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

    def _prune(self, seen_chunks: dict[str, RetrievedChunk]) -> tuple[list[RetrievedChunk], int | None]:
        """Top-N by score across every call, not their union (specs/5-
        adaptive-retrieval: citation precision dilutes as the accumulated
        set grows). None discarded, not zero, when pruning isn't configured
        at all -- distinct from pruning running and finding nothing to cut."""
        chunks = list(seen_chunks.values())
        if self.prune_top_n is None:
            return chunks, None
        if len(chunks) <= self.prune_top_n:
            return chunks, 0

        ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
        retained = ranked[: self.prune_top_n]
        return retained, len(chunks) - len(retained)

    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT_TIGHT_CITATIONS if self.tight_citations else SYSTEM_PROMPT

    def _build_messages(self, history: list[ConversationTurn], question: str) -> list[Message]:
        messages = [Message(role="system", content=self._system_prompt())]
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
        retained, discarded = self._prune(state.seen_chunks)

        return PipelineResult(
            answer=answer_text,
            stop_reason=completion.stop_reason,
            usage=completion.usage,
            latency_s=latency_s,
            request_params=completion.request_params,
            retrieved=[c.chunk_id for c in retained],
            retrieved_scores=[c.score for c in retained],
            cited=cited,
            retrieval_calls=state.call_count,
            capped=state.capped,
            pruned_discarded=discarded,
        )
