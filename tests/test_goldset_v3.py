"""Schema v3 specifics: turns validation, question/history/is_follow_up
properties, and the not-in-collection tag."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from raglab.evals.goldset import AnswerLocation, GoldEntry, GoldSetError, Source, Turn, load_gold_set


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "gold.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def _source() -> Source:
    return Source(doc="doc.md", answer_location=AnswerLocation(type="line_range", start=1, end=1))


def test_single_turn_entry_question_and_history():
    entry = GoldEntry(
        id="q-001", turns=[Turn(question="What is X?")], expected_answer="Y", sources=[_source()], tags=[]
    )
    assert entry.question == "What is X?"
    assert entry.history == []
    assert entry.is_follow_up is False


def test_follow_up_entry_question_is_final_turn_history_is_prior_turns():
    entry = GoldEntry(
        id="q-031",
        turns=[
            Turn(question="What is X?", answer="X is Y."),
            Turn(question="What about Z?"),
        ],
        expected_answer="Z is W.",
        sources=[_source()],
        tags=["follow-up"],
    )
    assert entry.question == "What about Z?"
    assert entry.history == [Turn(question="What is X?", answer="X is Y.")]
    assert entry.is_follow_up is True


def test_prior_turn_missing_answer_is_rejected():
    with pytest.raises(ValidationError):
        GoldEntry(
            id="q-031",
            turns=[Turn(question="What is X?"), Turn(question="What about Z?")],
            expected_answer="Z is W.",
            sources=[_source()],
            tags=[],
        )


def test_final_turn_with_scripted_answer_is_rejected():
    with pytest.raises(ValidationError):
        GoldEntry(
            id="q-031",
            turns=[Turn(question="What is X?", answer="X is Y.")],
            expected_answer="Y",
            sources=[_source()],
            tags=[],
        )


def test_zero_turns_is_rejected():
    with pytest.raises(ValidationError):
        GoldEntry(id="q-001", turns=[], expected_answer="Y", sources=[_source()], tags=[])


def test_follow_up_gold_set_loads(tmp_path):
    gold = load_gold_set(
        _write(
            tmp_path,
            """
            version: 3
            collection: everything
            corpus_hashes:
              doc.md: "sha256:deadbeef"
            entries:
              - id: q-031
                turns:
                  - question: "What is X?"
                    answer: "X is Y."
                  - question: "What about Z?"
                expected_answer: "Z is W."
                sources:
                  - doc: doc.md
                    answer_location: { type: line_range, start: 1, end: 1 }
                tags: [follow-up]
            """,
        )
    )
    [entry] = gold.entries
    assert entry.is_follow_up is True
    assert entry.question == "What about Z?"


def test_not_in_collection_tag_accepted_in_vocabulary(tmp_path):
    from raglab.evals.goldset import check_tag_vocabulary

    gold = load_gold_set(
        _write(
            tmp_path,
            """
            version: 3
            collection: rules
            corpus_hashes:
              doc.md: "sha256:deadbeef"
            entries:
              - id: q-001
                turns:
                  - question: "Answerable elsewhere, not here"
                expected_answer: "An answer that lives in another collection."
                sources:
                  - doc: doc.md
                    answer_location: { type: line_range, start: 1, end: 1 }
                tags: [not-in-collection]
            """,
        )
    )
    assert check_tag_vocabulary(gold) == []
