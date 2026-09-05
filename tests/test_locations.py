"""AnswerLocation -> char span resolution: line_range, char_span, section.

The nested rule-ID case (`A1.1` as a literal prefix of `A1.1.1`) is the trap
plan.md calls out explicitly: a naive substring search would anchor to the
wrong rule.
"""

from __future__ import annotations

import pytest

from raglab.evals.goldset import AnswerLocation
from raglab.evals.locations import line_of_offset, resolve_answer_location


def test_line_range_single_line():
    text = "line one\nline two\nline three\n"
    loc = AnswerLocation(type="line_range", start=2, end=2)
    [span] = resolve_answer_location(loc, text)
    assert text[span[0] : span[1]] == "line two\n"


def test_line_range_multiple_lines():
    text = "line one\nline two\nline three\n"
    loc = AnswerLocation(type="line_range", start=1, end=2)
    [span] = resolve_answer_location(loc, text)
    assert text[span[0] : span[1]] == "line one\nline two\n"


def test_line_range_last_line_no_trailing_newline():
    text = "line one\nline two"
    loc = AnswerLocation(type="line_range", start=2, end=2)
    [span] = resolve_answer_location(loc, text)
    assert text[span[0] : span[1]] == "line two"


def test_line_range_out_of_bounds_raises():
    text = "only one line"
    loc = AnswerLocation(type="line_range", start=5, end=6)
    with pytest.raises(ValueError):
        resolve_answer_location(loc, text)


def test_char_span_passes_through():
    text = "hello world"
    loc = AnswerLocation(type="char_span", start=6, end=11)
    [span] = resolve_answer_location(loc, text)
    assert span == (6, 11)


def test_char_span_out_of_bounds_raises():
    text = "hello"
    loc = AnswerLocation(type="char_span", start=0, end=100)
    with pytest.raises(ValueError):
        resolve_answer_location(loc, text)


def test_section_nested_rule_id_anchors_correctly():
    """A1.1 is a literal prefix of A1.1.1 -- must not anchor inside it."""
    text = "Some intro.\n\nA1.1 First rule text here.\n\nA1.1.1 Nested rule text.\n\nA1.2 Next rule.\n"
    loc = AnswerLocation(type="section", value=["A1.1"])
    [span] = resolve_answer_location(loc, text)
    section_text = text[span[0] : span[1]]
    assert section_text.startswith("A1.1 First rule")
    assert "A1.1.1" not in section_text  # boundary stopped before the nested rule


def test_section_extends_to_next_rule_id_boundary():
    text = "A4.4.1 Team members must be 16.\n\nA4.5.1 Drivers need a license.\n"
    loc = AnswerLocation(type="section", value=["A4.4.1"])
    [span] = resolve_answer_location(loc, text)
    assert text[span[0] : span[1]] == "A4.4.1 Team members must be 16.\n\n"


def test_section_extends_to_next_markdown_heading():
    text = "## First Heading\n\nSome body text about the first topic.\n\n## Second Heading\n\nMore text.\n"
    loc = AnswerLocation(type="section", value=["First Heading"])
    [span] = resolve_answer_location(loc, text)
    section_text = text[span[0] : span[1]]
    assert "Some body text" in section_text
    assert "Second Heading" not in section_text


def test_section_multiple_anchors_produce_multiple_spans():
    text = "A1.1 First.\n\nA1.2 Second.\n\nA1.3 Third.\n"
    loc = AnswerLocation(type="section", value=["A1.1", "A1.3"])
    spans = resolve_answer_location(loc, text)
    assert len(spans) == 2
    assert text[spans[0][0] : spans[0][1]].startswith("A1.1")
    assert text[spans[1][0] : spans[1][1]].startswith("A1.3")


def test_section_no_match_is_unscoreable():
    text = "A1.1 First rule.\n"
    loc = AnswerLocation(type="section", value=["Z9.9"])
    with pytest.raises(ValueError, match="no match"):
        resolve_answer_location(loc, text)


def test_section_ambiguous_match_is_unscoreable():
    text = "General note.\n\nA1.1 First mention.\n\nSee also A1.1 again here.\n"
    loc = AnswerLocation(type="section", value=["A1.1"])
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_answer_location(loc, text)


def test_line_of_offset_basic():
    text = "aaa\nbbb\nccc"
    assert line_of_offset(text, 0) == 1
    assert line_of_offset(text, 4) == 2
    assert line_of_offset(text, 10) == 3
