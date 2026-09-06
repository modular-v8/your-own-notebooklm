"""The `)` cross-reference guard: PDF line-wrapping can push a mid-sentence
"(see CV3.2.1)." onto its own line, making it look line-initial. Real case:
fb_rules.pdf's CV3.2.1 (see specs/3-collections/spec.md acceptance criteria).
"""

from __future__ import annotations

import pytest

from raglab.evals.goldset import AnswerLocation
from raglab.evals.locations import find_matches, resolve_answer_location


def test_paren_followed_match_excluded_from_resolution():
    """Two line-initial-looking matches, one a wrapped cross-reference --
    without the guard this would be ambiguous; with it, it resolves alone."""
    text = (
        "CV3.2.1 The maximum sound level test speed is 110 dB(C).\n\n"
        "The vehicle must be compliant at all speeds up to the maximum test speed (see\n"
        "CV3.2.1).\n"
    )
    loc = AnswerLocation(type="section", value=["CV3.2.1"])
    [span] = resolve_answer_location(loc, text)
    assert text[span[0] : span[1]].startswith("CV3.2.1 The maximum sound level")


def test_paren_followed_match_alone_is_no_match():
    text = "Intro.\n\nAs noted (see\nCV3.2.1).\n"
    loc = AnswerLocation(type="section", value=["CV3.2.1"])
    with pytest.raises(ValueError, match="no line-initial match"):
        resolve_answer_location(loc, text)


def test_find_matches_reports_cross_reference_flag():
    text = "CV3.2.1 Real rule text.\n\nSee (see\nCV3.2.1).\n"
    matches = find_matches(text, "CV3.2.1")
    assert len(matches) == 2
    assert matches[0].cross_reference is False
    assert matches[1].cross_reference is True
    assert matches[1].line_initial is True  # line-initial *and* a cross-reference
