"""Line-initial `section` matching and the `occurrence` selector.

The real motivating case: `EV6.1.2` appears once as the actual rule and
twice more as a mid-sentence cross-reference ("...defined in EV6.1.2
must..."). Restricting matches to line-initial occurrences drops the
cross-references; `occurrence` then resolves any genuine line-initial
ambiguity, like a rule id that also appears in a document's own changelog.
"""

from __future__ import annotations

import pytest

from raglab.evals.goldset import AnswerLocation
from raglab.evals.locations import find_matches, resolve_answer_location


def test_mid_sentence_cross_reference_produces_no_match():
    text = "Intro text.\n\nThe shutdown circuit defined in EV6.1.2 must remain closed.\n"
    loc = AnswerLocation(type="section", value=["EV6.1.2"])
    with pytest.raises(ValueError, match="no line-initial match"):
        resolve_answer_location(loc, text)


def test_mid_sentence_reference_alongside_real_rule_is_not_ambiguous():
    """The one line-initial occurrence wins outright; the cross-reference
    doesn't count toward ambiguity at all."""
    text = (
        "EV6.1.2 The shutdown circuit must include the BSPD.\n\n"
        "As referenced in EV6.1.2, this is mandatory.\n"
    )
    loc = AnswerLocation(type="section", value=["EV6.1.2"])
    [span] = resolve_answer_location(loc, text)
    assert text[span[0] : span[1]].startswith("EV6.1.2 The shutdown circuit")


def test_occurrence_first_selects_changelog_mention():
    text = "A4.4.1 changed the minimum age to 16.\n\nA4.4.1 Team members must be 16.\n"
    loc = AnswerLocation(type="section", value=["A4.4.1"], occurrence="first")
    [span] = resolve_answer_location(loc, text)
    assert "changed the minimum age" in text[span[0] : span[1]]


def test_occurrence_last_selects_rulebook_body():
    text = "A4.4.1 changed the minimum age to 16.\n\nA4.4.1 Team members must be 16.\n"
    loc = AnswerLocation(type="section", value=["A4.4.1"], occurrence="last")
    [span] = resolve_answer_location(loc, text)
    assert "Team members must be 16" in text[span[0] : span[1]]


def test_occurrence_index_selects_nth_match():
    text = "A1.1 First.\n\nA1.1 Second.\n\nA1.1 Third.\n"
    loc = AnswerLocation(type="section", value=["A1.1"], occurrence=2)
    [span] = resolve_answer_location(loc, text)
    assert text[span[0] : span[1]].startswith("A1.1 Second")


def test_occurrence_out_of_range_raises():
    text = "A1.1 Only one.\n"
    loc = AnswerLocation(type="section", value=["A1.1"], occurrence=2)
    with pytest.raises(ValueError, match="out of range"):
        resolve_answer_location(loc, text)


def test_occurrence_applies_per_anchor_independently():
    """["T11.6", "T11.6.1"] needs last for one anchor and is a no-op
    (single match) for the other -- occurrence is a per-anchor selector,
    not a single choice applied once to the whole answer_location."""
    text = "T11.6 heading text.\n\nT11.6.1 changelog note.\n\nT11.6.1 actual rule body.\n"
    loc = AnswerLocation(type="section", value=["T11.6", "T11.6.1"], occurrence="last")
    spans = resolve_answer_location(loc, text)
    assert len(spans) == 2
    assert text[spans[0][0] : spans[0][1]].startswith("T11.6 heading")
    assert text[spans[1][0] : spans[1][1]].startswith("T11.6.1 actual rule body")


def test_find_matches_reports_line_initial_flag():
    text = "EV6.1.2 The shutdown circuit must include the BSPD.\n\nAs referenced in EV6.1.2, mandatory.\n"
    matches = find_matches(text, "EV6.1.2")
    assert len(matches) == 2
    assert matches[0].line_initial is True
    assert matches[1].line_initial is False
    assert matches[0].line == 1
    assert matches[1].line == 3


def test_find_matches_empty_when_no_occurrence():
    assert find_matches("nothing relevant here", "Z9.9") == []
