"""Query rewriting: resolve a follow-up's referents into a standalone
retrieval query, one provider call (specs/4-retrieval-optimization). This is
the phase's answer to the follow-up recall deficit Phase 3 measured (30-31
points, standalone vs. follow-up) -- a narrow, single-purpose crossing of the
history/retrieval boundary `pipelines/base.py` deliberately keeps closed
otherwise: the rewritten string is used only to build the retrieval query,
never to change what the final answer call sees (which still gets the raw
history and raw final question, unchanged).

No-op on a standalone entry (empty history) -- the provider is not called
at all, so this can never cost anything or change behavior on the 47
standalone entries in `fb_rules`.
"""

from __future__ import annotations

from ..pipelines.base import ConversationTurn
from ..providers.base import LLMProvider, Message

REWRITE_PROMPT = """A user is asking a follow-up question in an ongoing conversation. Rewrite \
it as a standalone question that makes sense with no prior context, by \
resolving every pronoun and implicit reference (e.g. "it", "that", "the one \
before it") using the conversation history below. Preserve the follow-up's \
actual intent exactly -- do not answer it, narrow it, or expand its scope.

CONVERSATION HISTORY:
{history}

FOLLOW-UP QUESTION:
{question}

Respond with ONLY the rewritten standalone question, no other text.
"""


def _format_history(history: list[ConversationTurn]) -> str:
    return "\n".join(f"Q: {turn.question}\nA: {turn.answer}" for turn in history)


class QueryRewriter:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def rewrite(self, history: list[ConversationTurn], question: str) -> str | None:
        """Returns None on a no-op (no history to resolve against) so the
        caller can tell "rewriting didn't fire" from "rewriting fired and
        happened to return the same text" without a second comparison."""
        if not history:
            return None

        prompt = REWRITE_PROMPT.format(history=_format_history(history), question=question)
        completion = await self.provider.complete([Message(role="user", content=prompt)])
        rewritten = completion.text.strip()
        return rewritten or question
