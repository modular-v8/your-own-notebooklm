"""Verdict parsing, including the unparseable/invalid -> ungraded path."""

from __future__ import annotations

import pytest

from raglab.evals.judge import Judge
from tests.fakes import FakeProvider, text_completion


@pytest.mark.asyncio
async def test_groundedness_verdict_parses():
    provider = FakeProvider([text_completion('{"verdict": "grounded", "rationale": "matches"}')])
    judge = Judge(provider)
    result = await judge.score_groundedness("Q?", "expected", None, "candidate")
    assert result.verdict == "grounded"
    assert result.rationale == "matches"


@pytest.mark.asyncio
async def test_refusal_verdict_parses():
    provider = FakeProvider([text_completion('{"verdict": "refused_correctly", "rationale": "declined"}')])
    judge = Judge(provider)
    result = await judge.score_refusal("Q?", "I cannot answer from the document.")
    assert result.verdict == "refused_correctly"


@pytest.mark.asyncio
async def test_unparseable_output_is_ungraded():
    provider = FakeProvider([text_completion("not json at all")])
    judge = Judge(provider)
    result = await judge.score_groundedness("Q?", "expected", None, "candidate")
    assert result.verdict is None
    assert "unparseable" in result.rationale


@pytest.mark.asyncio
async def test_invalid_verdict_value_is_ungraded():
    provider = FakeProvider([text_completion('{"verdict": "maybe", "rationale": "unsure"}')])
    judge = Judge(provider)
    result = await judge.score_groundedness("Q?", "expected", None, "candidate")
    assert result.verdict is None


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_parsed():
    provider = FakeProvider([text_completion('```json\n{"verdict": "grounded", "rationale": "ok"}\n```')])
    judge = Judge(provider)
    result = await judge.score_groundedness("Q?", "expected", None, "candidate")
    assert result.verdict == "grounded"
