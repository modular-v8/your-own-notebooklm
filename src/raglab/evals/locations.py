"""AnswerLocation -> character spans in extracted text.

Every variant normalizes to a list of half-open `(start, end)` spans (the
same `text[start:end]` convention the chunker uses). `section` can produce
more than one span -- one per anchor in `value` -- the rest exactly one.

Traps this module exists to avoid (see plan.md):

- **Nested rule-ID anchors.** `A1.1` is a literal prefix of `A1.1.1`,
  and the Formula Bharat corpus has 2,269 such IDs. A naive substring
  search anchors to the wrong rule. Boundary guards `(?<![\\w.])` /
  `(?![\\w.])` on both sides of the anchor prevent a match from landing
  inside a longer ID.
- **Ambiguous anchors are a validation failure, not a best guess.** An
  anchor matching zero or more-than-one times (after the line-initial
  filter below) is reported as unscoreable rather than silently picking
  the first match -- unless an explicit `occurrence` selector says which
  one to take.
- **A `section` anchor only counts where it begins a line.** Restricting
  to line-initial matches (permitting leading whitespace and Markdown
  heading markers) drops mid-sentence cross-references like "...defined in
  EV6.1.2 must be..." that would otherwise inflate the ambiguity count.
- **PDF line-wrapping can push a cross-reference to column zero.** "...up
  to the maximum test speed (see\nCV3.2.1)." wraps the closing paren onto
  its own line, which makes "CV3.2.1)." line-initial too. An anchor match
  immediately followed by `)` is a cross-reference wearing a disguise, not
  a second occurrence of the rule -- it's excluded from the match set
  entirely, before the line-initial filter even runs.

Resolution happens at validation time, before any model call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..parsers.registry import ExtractedDocument
from .goldset import AnswerLocation, GoldSet

CharSpan = tuple[int, int]
# A gold span tagged with the document it belongs to -- required once an
# entry's sources can span more than one document, so overlap checks never
# compare offsets from unrelated documents.
GoldSpan = tuple[str, CharSpan]

# A rule-ID-shaped token: 1-3 uppercase letters, a leading number, then one
# or more dot-separated numeric segments (A4.4.1, CV4.1.2, T11.4.3, ...).
RULE_ID_RE = re.compile(r"(?<![\w.])[A-Z]{1,3}\d+(?:\.\d+)+(?![\w.])")
HEADING_RE = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)
# Leading whitespace and/or Markdown heading markers are allowed before an
# anchor still counts as "beginning a line".
LINE_INITIAL_PREFIX_RE = re.compile(r"[#\s]*")


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


def _is_line_initial(text: str, match_start: int) -> bool:
    line_start = text.rfind("\n", 0, match_start) + 1
    prefix = text[line_start:match_start]
    return LINE_INITIAL_PREFIX_RE.fullmatch(prefix) is not None


def _is_cross_reference(text: str, match_end: int) -> bool:
    """A match immediately followed by `)` is a cross-reference like
    "(see CV3.2.1)." -- never the rule's own heading, however it wrapped."""
    return match_end < len(text) and text[match_end] == ")"


def _line_snippet(text: str, match_start: int) -> str:
    line_start = text.rfind("\n", 0, match_start) + 1
    line_end = text.find("\n", match_start)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip()


def _next_boundary(text: str, from_pos: int) -> int:
    heading = HEADING_RE.search(text, from_pos)
    rule_id = RULE_ID_RE.search(text, from_pos)
    candidates = [m.start() for m in (heading, rule_id) if m is not None]
    return min(candidates) if candidates else len(text)


@dataclass(frozen=True)
class AnchorMatch:
    line: int
    line_initial: bool
    cross_reference: bool
    snippet: str


def find_matches(text: str, anchor: str) -> list[AnchorMatch]:
    """Every raw occurrence of `anchor`, in document order, using the same
    boundary regex `section` resolution uses -- unfiltered by line-initial
    or cross-reference status, both reported per-match instead so `gold
    locate` can show a gold-set author exactly why an anchor is or isn't
    ambiguous."""
    matches = []
    for m in _anchor_pattern(anchor).finditer(text):
        matches.append(
            AnchorMatch(
                line=line_of_offset(text, m.start()),
                line_initial=_is_line_initial(text, m.start()),
                cross_reference=_is_cross_reference(text, m.end()),
                snippet=_line_snippet(text, m.start()),
            )
        )
    return matches


def _select_occurrence(
    matches: list[re.Match[str]], occurrence: str | int, anchor: str
) -> re.Match[str]:
    if occurrence == "first":
        return matches[0]
    if occurrence == "last":
        return matches[-1]
    if isinstance(occurrence, int):
        index = occurrence - 1
        if index < 0 or index >= len(matches):
            raise ValueError(
                f"anchor {anchor!r}: occurrence {occurrence} out of range ({len(matches)} line-initial matches)"
            )
        return matches[index]
    raise ValueError(f"anchor {anchor!r}: invalid occurrence {occurrence!r}")


def resolve_section(
    text: str, anchors: list[str], occurrence: str | int | None = None
) -> list[CharSpan]:
    spans: list[CharSpan] = []
    for anchor in anchors:
        all_matches = list(_anchor_pattern(anchor).finditer(text))
        candidate_matches = [m for m in all_matches if not _is_cross_reference(text, m.end())]
        line_initial_matches = [m for m in candidate_matches if _is_line_initial(text, m.start())]

        if not line_initial_matches:
            reason = (
                "no match"
                if not all_matches
                else "no line-initial match (only mid-sentence references or cross-references)"
            )
            raise ValueError(f"anchor {anchor!r}: {reason}")

        if occurrence is None:
            if len(line_initial_matches) != 1:
                raise ValueError(f"anchor {anchor!r}: {len(line_initial_matches)} ambiguous matches")
            match = line_initial_matches[0]
        else:
            match = _select_occurrence(line_initial_matches, occurrence, anchor)

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
        return resolve_section(text, location.value, location.occurrence)
    raise ValueError(f"unknown answer_location type {location.type!r}")


def resolve_gold_locations(
    gold: GoldSet, extracted: dict[str, ExtractedDocument]
) -> tuple[dict[str, list[GoldSpan]], list[str]]:
    """Resolve every entry's sources into doc-tagged spans; collect
    unscoreable entries rather than raising.

    Entries tagged not-in-document have no sources and are skipped -- they
    aren't scoreable for recall, but that's expected, not an error. An
    entry with several sources contributes one span per source, each
    tagged with that source's own document, so overlap checks downstream
    never compare offsets across unrelated documents.
    """
    spans: dict[str, list[GoldSpan]] = {}
    errors: list[str] = []
    for entry in gold.entries:
        if not entry.sources:
            continue
        entry_spans: list[GoldSpan] = []
        entry_errors: list[str] = []
        for source in entry.sources:
            text = extracted[source.doc].text
            try:
                for span in resolve_answer_location(source.answer_location, text):
                    entry_spans.append((source.doc, span))
            except ValueError as exc:
                entry_errors.append(f"{entry.id} ({source.doc}): {exc}")
        if entry_errors:
            errors.extend(entry_errors)
        else:
            spans[entry.id] = entry_spans
    return spans, errors
