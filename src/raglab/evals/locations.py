"""AnswerLocation -> character spans in extracted text.

Every variant normalizes to a list of half-open `(start, end)` spans (the
same `text[start:end]` convention the chunker uses). `section` can produce
more than one span — one per anchor in `value` — the rest exactly one.

Two traps this module exists to avoid (see plan.md):

- **Nested rule-ID anchors.** `A1.1` is a literal prefix of `A1.1.1`,
  and the Formula Bharat corpus has 2,269 such IDs. A naive substring
  search anchors to the wrong rule. Boundary guards `(?<![\\w.])` /
  `(?![\\w.])` on both sides of the anchor prevent a match from landing
  inside a longer ID.
- **Ambiguous anchors are a validation failure, not a best guess.** An
  anchor matching zero or more-than-one times is reported as unscoreable
  rather than silently picking the first match.

Resolution happens at validation time, before any model call.
"""

from __future__ import annotations

import re

from ..parsers.registry import ExtractedDocument
from .goldset import AnswerLocation, GoldSet

CharSpan = tuple[int, int]

# A rule-ID-shaped token: 1-3 uppercase letters, a leading number, then one
# or more dot-separated numeric segments (A4.4.1, CV4.1.2, T11.4.3, ...).
RULE_ID_RE = re.compile(r"(?<![\w.])[A-Z]{1,3}\d+(?:\.\d+)+(?![\w.])")
HEADING_RE = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)


def line_offsets(text: str) -> list[int]:
    """offsets[i] = char offset where 1-indexed line (i+1) begins."""
    offsets = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def line_of_offset(text: str, offset: int) -> int:
    """1-indexed line number containing `offset`."""
    offsets = line_offsets(text)
    lo, hi = 0, len(offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if offsets[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def resolve_line_range(text: str, start_line: int, end_line: int) -> CharSpan:
    offsets = line_offsets(text)
    n_lines = len(offsets)
    if start_line < 1 or end_line < start_line or start_line > n_lines:
        raise ValueError(f"line range {start_line}-{end_line} out of bounds ({n_lines} lines)")
    char_start = offsets[start_line - 1]
    char_end = offsets[end_line] if end_line < n_lines else len(text)
    return char_start, char_end


def resolve_char_span(text: str, start: int, end: int) -> CharSpan:
    if start < 0 or end > len(text) or start >= end:
        raise ValueError(f"char_span {start}-{end} out of bounds (document length {len(text)})")
    return start, end


def _anchor_pattern(anchor: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w.]){re.escape(anchor)}(?![\w.])")


def _next_boundary(text: str, from_pos: int) -> int:
    heading = HEADING_RE.search(text, from_pos)
    rule_id = RULE_ID_RE.search(text, from_pos)
    candidates = [m.start() for m in (heading, rule_id) if m is not None]
    return min(candidates) if candidates else len(text)


def resolve_section(text: str, anchors: list[str]) -> list[CharSpan]:
    spans: list[CharSpan] = []
    for anchor in anchors:
        matches = list(_anchor_pattern(anchor).finditer(text))
        if len(matches) != 1:
            reason = "no match" if not matches else f"{len(matches)} ambiguous matches"
            raise ValueError(f"anchor {anchor!r}: {reason}")
        match = matches[0]
        end = _next_boundary(text, match.end())
        spans.append((match.start(), end))
    return spans


def resolve_answer_location(location: AnswerLocation, text: str) -> list[CharSpan]:
    if location.type == "line_range":
        assert location.start is not None and location.end is not None
        return [resolve_line_range(text, location.start, location.end)]
    if location.type == "char_span":
        assert location.start is not None and location.end is not None
        return [resolve_char_span(text, location.start, location.end)]
    if location.type == "section":
        assert location.value is not None
        return resolve_section(text, location.value)
    raise ValueError(f"unknown answer_location type {location.type!r}")


def resolve_gold_locations(
    gold: GoldSet, extracted: dict[str, ExtractedDocument]
) -> tuple[dict[str, list[CharSpan]], list[str]]:
    """Resolve every entry's answer_location; collect unscoreable entries rather than raising.

    Entries tagged not-in-document have no answer_location and are skipped —
    they aren't scoreable for recall, but that's expected, not an error.
    """
    spans: dict[str, list[CharSpan]] = {}
    errors: list[str] = []
    for entry in gold.entries:
        if entry.answer_location is None:
            continue
        text = extracted[entry.doc].text
        try:
            spans[entry.id] = resolve_answer_location(entry.answer_location, text)
        except ValueError as exc:
            errors.append(f"{entry.id} ({entry.doc}): {exc}")
    return spans, errors
