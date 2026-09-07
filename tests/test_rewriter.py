"""Query rewriting via FakeProvider (specs/4-retrieval-optimization T5.1)."""

from __future__ import annotations

import pytest

from raglab.pipelines.base import ConversationTurn
from raglab.retrieval.rewriter import QueryRewriter
from tests.fakes import FakeProvider, text_completion


@pytest.mark.asyncio
async def test_no_op_on_standalone_question_provider_never_called():
    provider = FakeProvider([])  # no scripted response: must not be called
    rewriter = QueryRewriter(provider)

    result = await rewriter.rewrite([], "What is the minimum age for a team member?")

    assert result is None
    assert provider.calls == []


@pytest.mark.asyncio
async def test_resolves_referent_on_follow_up():
    history = [
        ConversationTurn(
            question="Which cars used the SMG III, and in what years was it in operation?",
            answer="SMG III was used in the E60 M5 and E63/E64 M6, operating from roughly 2005 to 2010.",
        )
    ]
    rewritten_text = "What transmission preceded the SMG III used in the E60 M5 and E63/E64 M6?"
    provider = FakeProvider([text_completion(rewritten_text)])
    rewriter = QueryRewriter(provider)

    result = await rewriter.rewrite(history, "What about the one before it?")

    assert result == rewritten_text
    assert len(provider.calls) == 1
    prompt = provider.calls[0][0].content
    assert "SMG III" in prompt
    assert "What about the one before it?" in prompt


@pytest.mark.asyncio
async def test_falls_back_to_original_question_on_empty_rewrite():
    history = [ConversationTurn(question="Q1?", answer="A1.")]
    provider = FakeProvider([text_completion("   ")])
    rewriter = QueryRewriter(provider)

    result = await rewriter.rewrite(history, "the follow-up")

    assert result == "the follow-up"
