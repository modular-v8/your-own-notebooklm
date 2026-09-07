"""Verdict parsing, including the unparseable/invalid -> ungraded path."""

from __future__ import annotations

import pytest

from raglab.evals.judge import Judge
from tests.fakes import FakeProvider, text_completion


@pytest.mark.asyncio
async def test_groundedness_verdict_parses():
    provider = FakeProvider([text_completion('{"verdict": "grounded", "rationale": "matches"}')])
    judge = Judge(provider)
    result = await judge.score_groundedness("Q?", "expected", [], "candidate")
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
    result = await judge.score_groundedness("Q?", "expected", [], "candidate")
    assert result.verdict is None
    assert "unparseable" in result.rationale


@pytest.mark.asyncio
async def test_invalid_verdict_value_is_ungraded():
    provider = FakeProvider([text_completion('{"verdict": "maybe", "rationale": "unsure"}')])
    judge = Judge(provider)
    result = await judge.score_groundedness("Q?", "expected", [], "candidate")
    assert result.verdict is None


@pytest.mark.asyncio
async def test_embedded_unescaped_quote_in_rationale_is_recovered():
    """The one recurring real-world failure: the model quotes a phrase with a
    literal " instead of \\", breaking strict JSON but still recoverable."""
    broken = '{"verdict": "grounded", "rationale": "matches the "rough first attempt" phrasing"}'
    provider = FakeProvider([text_completion(broken)])
    judge = Judge(provider)
    result = await judge.score_groundedness("Q?", "expected", [], "candidate")
    assert result.verdict == "grounded"
    assert "rough first attempt" in result.rationale


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_parsed():
    provider = FakeProvider([text_completion('```json\n{"verdict": "grounded", "rationale": "ok"}\n```')])
    judge = Judge(provider)
    result = await judge.score_groundedness("Q?", "expected", [], "candidate")
    assert result.verdict == "grounded"


# Phase 4 hedged-answer rubric (specs/4-retrieval-optimization/plan.md,
# As-built notes: T1.1). Two real cases showed opposite verdicts on the same
# shape of answer -- one correctly declines part of a question while
# correctly answering the rest. The rubric now says both are "grounded". The
# prompt assertions below pin that the rubric text is actually present:
# against the pre-fix prompt they fail, since that guidance didn't exist.

_HEDGE_RUBRIC_MARKER = "explicitly declines rather than fabricates"


@pytest.mark.asyncio
async def test_tiptronic_q005_hedge_is_grounded():
    """Phase 2's tiptronic q-005: judged not_grounded once, for correctly
    declining a fact (the Aston Martin DB9 exception) that was never
    retrieved, while correctly answering the part that was."""
    question = (
        "Did every manufacturer's Tiptronic-style manual mode give the computer "
        "final override authority over the driver?"
    )
    expected_answer = (
        "Not every one. Most did, but Aston Martin's version in the DB9 loosened "
        "that leash further, holding a gear at redline instead of shifting up for "
        "the driver and blipping the throttle on downshifts, giving the driver "
        "more actual authority than Porsche's own original design did."
    )
    candidate_answer = (
        "I can only confirm this for Audi's Tiptronic specifically -- it still "
        "upshifts itself even in manual mode and forces an upshift at redline. I "
        "cannot say from the provided material whether this override authority "
        "was universal across every manufacturer's version."
    )
    provider = FakeProvider([text_completion('{"verdict": "grounded", "rationale": "honest partial answer"}')])
    judge = Judge(provider)

    result = await judge.score_groundedness(question, expected_answer, [], candidate_answer)

    assert result.verdict == "grounded"
    assert _HEDGE_RUBRIC_MARKER in provider.calls[0][0].content


@pytest.mark.asyncio
async def test_fb_rules_q011_hedge_is_grounded():
    """Phase 3's fb_rules q-011: already judged grounded despite
    recall_hit=False and citation_precision=0.0 -- declines to name the BSPD
    acronym expansion while correctly and fully describing what it does."""
    question = "What does BSPD stand for and what is it required to do?"
    expected_answer = (
        "BSPD stands for Brake System Plausibility Device. It is a standalone, "
        "non-programmable circuit that must open the shutdown circuit when hard "
        "braking occurs while, on an EV, 5 kW or more of power is being "
        "delivered to the motors, or on a CV, the throttle position is more "
        "than 25% over idle."
    )
    candidate_answer = (
        "I cannot find an explicit statement of what 'BSPD' stands for as an "
        "acronym -- the rules text uses 'BSPD' without spelling it out. However, "
        "the excerpts do describe what the BSPD is required to do: it must open "
        "the shutdown circuit if throttle position is more than 25% over idle "
        "while a braking condition is met, and it must be directly supplied "
        "from the LVMS."
    )
    provider = FakeProvider([text_completion('{"verdict": "grounded", "rationale": "honest partial answer"}')])
    judge = Judge(provider)

    result = await judge.score_groundedness(question, expected_answer, [], candidate_answer)

    assert result.verdict == "grounded"
    assert _HEDGE_RUBRIC_MARKER in provider.calls[0][0].content
