"""LLM-as-judge: scores groundedness or refusal correctness via strict-prompt JSON.

Per-provider structured output (tool-forced JSON) was deferred: until real
runs exist against a gold set, strict-prompt JSON is simpler and uniform
across all three providers, and an unparseable verdict is already a defined
path (marked ungraded, excluded from aggregates) rather than a crash.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from .goldset import AnswerLocation
from ..providers.base import LLMProvider, Message

Verdict = Literal["grounded", "not_grounded", "refused_correctly", "refused_incorrectly"]
VALID_VERDICTS = frozenset(Verdict.__args__)

GROUNDEDNESS_PROMPT = """You are grading whether a CANDIDATE answer is grounded in a SOURCE document.

QUESTION:
{question}

EXPECTED ANSWER (from the source document):
{expected_answer}

SOURCE LOCATION:
{source_location}

CANDIDATE ANSWER:
{candidate_answer}

Judge whether the candidate answer is factually consistent with the expected
answer and not fabricated beyond what the source location supports.

Respond with ONLY a JSON object, no other text:
{{"verdict": "grounded" | "not_grounded", "rationale": "<one sentence>"}}
"""

REFUSAL_PROMPT = """You are grading whether a CANDIDATE answer correctly refuses to answer
a question that the source document does not address.

QUESTION:
{question}

CANDIDATE ANSWER:
{candidate_answer}

The document does NOT contain an answer to this question. A correct response
declines to answer from the document (it may say so explicitly, or express
that the information isn't present). An incorrect response provides a
substantive answer anyway, whether or not it happens to be true.

Respond with ONLY a JSON object, no other text:
{{"verdict": "refused_correctly" | "refused_incorrectly", "rationale": "<one sentence>"}}
"""


@dataclass(frozen=True)
class JudgeResult:
    verdict: Verdict | None  # None means ungraded: unparseable or invalid
    rationale: str


def _format_location(location: AnswerLocation | None) -> str:
    if location is None:
        return "(not applicable)"
    if location.type == "section":
        return f"section: {location.name}"
    return f"{location.type} {location.start}-{location.end}"


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.removeprefix("json").strip()
    return stripped


class Judge:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def score_groundedness(
        self,
        question: str,
        expected_answer: str,
        source_location: AnswerLocation | None,
        candidate_answer: str,
    ) -> JudgeResult:
        prompt = GROUNDEDNESS_PROMPT.format(
            question=question,
            expected_answer=expected_answer,
            source_location=_format_location(source_location),
            candidate_answer=candidate_answer,
        )
        return await self._judge(prompt)

    async def score_refusal(self, question: str, candidate_answer: str) -> JudgeResult:
        prompt = REFUSAL_PROMPT.format(question=question, candidate_answer=candidate_answer)
        return await self._judge(prompt)

    async def _judge(self, prompt: str) -> JudgeResult:
        completion = await self.provider.complete([Message(role="user", content=prompt)])
        try:
            parsed = json.loads(_extract_json(completion.text))
            verdict = parsed["verdict"]
            rationale = str(parsed.get("rationale", ""))
        except (json.JSONDecodeError, KeyError, TypeError):
            return JudgeResult(verdict=None, rationale=f"unparseable judge output: {completion.text!r}")

        if verdict not in VALID_VERDICTS:
            return JudgeResult(verdict=None, rationale=f"invalid verdict {verdict!r}")
        return JudgeResult(verdict=verdict, rationale=rationale)
