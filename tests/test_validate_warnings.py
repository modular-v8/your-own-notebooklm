"""not-in-document lexical-match warning: catches the exact mistake the
original fb_rules.yaml q-027 and q-028 were (see specs/3-collections/spec.md
acceptance criteria: "verified by reintroducing the original q-027")."""

from __future__ import annotations

from pathlib import Path

from raglab.corpus import Document, hash_bytes
from raglab.evals.goldset import GoldEntry, GoldSet, Turn
from raglab.evals.validate import check_not_in_document_lexical_matches
from raglab.parsers.registry import ExtractedDocument
from raglab.parsers.text import TextParser


def _extracted(doc_name: str, text: str) -> ExtractedDocument:
    document = Document(name=doc_name, path=Path(doc_name), sha256=hash_bytes(text.encode()))
    return ExtractedDocument(document=document, parser=TextParser.identity, text=text)


def _gold(*entries: GoldEntry) -> GoldSet:
    return GoldSet(
        version=3,
        collection="everything",
        corpus_hashes={"fb_rules.pdf": "sha256:whatever"},
        entries=list(entries),
    )


REINTRODUCED_Q027 = GoldEntry(
    id="q-027",
    turns=[
        Turn(
            question="What is the maximum permitted sound level for a CV vehicle "
            "at the calculated test speed, and at idle?"
        )
    ],
    expected_answer=None,
    sources=[],
    tags=["not-in-document"],
)

CORPUS_TEXT = (
    "CV3.2.1\n"
    "The maximum sound level test speed for a given engine will be the engine speed that\n"
    "corresponds to an average piston speed of 15.25 m/s. The calculated speed will be rounded\n"
    "to the nearest 500 rpm. The maximum permitted sound level up to this calculated speed is\n"
    "110 dB(C), fast weighting.\n"
    "CV3.2.2\n"
    "At idle the maximum permitted sound level is 103 dB(C), fast weighting.\n"
)


def test_reintroduced_q027_triggers_warning_naming_matching_lines():
    gold = _gold(REINTRODUCED_Q027)
    warnings = check_not_in_document_lexical_matches(gold, {"fb_rules.pdf": _extracted("fb_rules.pdf", CORPUS_TEXT)})
    assert len(warnings) == 1
    assert "q-027" in warnings[0]
    assert "fb_rules.pdf" in warnings[0]
    # the answer line ("...maximum permitted sound level up to this...") is line 4
    assert "4" in warnings[0]


def test_genuinely_absent_entry_produces_no_warning():
    absent_entry = GoldEntry(
        id="q-029",
        turns=[Turn(question="Are there any rules governing where sponsor logos may be placed?")],
        expected_answer=None,
        sources=[],
        tags=["not-in-document"],
    )
    gold = _gold(absent_entry)
    warnings = check_not_in_document_lexical_matches(gold, {"fb_rules.pdf": _extracted("fb_rules.pdf", CORPUS_TEXT)})
    assert warnings == []


def test_entries_without_the_tag_are_never_checked():
    """Only not-in-document entries are candidates -- a normal, sourced
    entry is never a candidate even if its question shares vocabulary with
    the corpus (which, for a real entry, it always will)."""
    from raglab.evals.goldset import AnswerLocation, Source

    grounded_entry = GoldEntry(
        id="q-001",
        turns=[Turn(question="What is the maximum permitted sound level up to test speed?")],
        expected_answer="110 dB(C).",
        sources=[Source(doc="fb_rules.pdf", answer_location=AnswerLocation(type="line_range", start=1, end=1))],
        tags=[],
    )
    gold = _gold(grounded_entry)
    warnings = check_not_in_document_lexical_matches(gold, {"fb_rules.pdf": _extracted("fb_rules.pdf", CORPUS_TEXT)})
    assert warnings == []
