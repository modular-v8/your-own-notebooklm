"""Two chunking strategies, sharing one `Chunk` shape and one sub-splitter.

`chunk_text` (fixed-size): char spans preserved, no structure awareness.
900/150 is a recorded default, not a swept parameter — sweeping chunk size
is Phase 4's job and needs this phase's recall@k to already exist to
measure against. 900 chars leaves generous headroom under bge-small's
512-token truncation limit (~2,000 chars).

`chunk_text_structure` (specs/4-retrieval-optimization Milestone 6): splits
on rule-ID and Markdown-heading boundaries instead, then falls back to
`chunk_text`'s own windowing to sub-split any segment that would otherwise
exceed the 512-token limit. The boundary regexes intentionally mirror
`evals/locations.py`'s `RULE_ID_RE`/`HEADING_RE` -- both ask "where does the
next rule or heading begin", and a chunk boundary disagreeing with where
gold-anchor resolution thinks a rule starts would be a real bug. Kept as a
local copy rather than an import so `index/` doesn't depend on `evals/`,
the reverse of every other dependency in this codebase -- if one changes,
check the other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150

# Mirrors evals/locations.py's RULE_ID_RE / HEADING_RE -- see module docstring.
_RULE_ID_RE = re.compile(r"(?<![\w.])[A-Z]{1,3}\d+(?:\.\d+)+(?![\w.])")
_HEADING_RE = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)
_LINE_INITIAL_PREFIX_RE = re.compile(r"[#\s]*")

# ~2,000 chars is this file's own established conservative ceiling for
# bge-small's 512-token truncation limit (see docstring above); a segment
# under this is never sub-split, however it splits above it, using the same
# char-based estimate OverContextError does elsewhere in this codebase
# (providers/openrouter.py) -- approximate, deliberately conservative.
MAX_STRUCTURE_CHUNK_CHARS = 2000


@dataclass(frozen=True)
class Chunk:
    doc: str
    ordinal: int
    char_start: int
    char_end: int
    text: str

    @property
    def chunk_id(self) -> str:
        return f"{self.doc}:{self.ordinal:04d}"


def chunk_text(doc_name: str, text: str, *, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    if not text:
        return []

    step = size - overlap
    chunks: list[Chunk] = []
    start = 0
    ordinal = 0
    length = len(text)

    while start < length:
        end = min(start + size, length)
        chunks.append(Chunk(doc=doc_name, ordinal=ordinal, char_start=start, char_end=end, text=text[start:end]))
        ordinal += 1
        if end == length:
            break
        start += step

    return chunks


def _is_line_initial(text: str, pos: int) -> bool:
    line_start = text.rfind("\n", 0, pos) + 1
    return _LINE_INITIAL_PREFIX_RE.fullmatch(text[line_start:pos]) is not None


def _structural_boundaries(text: str) -> list[int]:
    """Char offsets where a rule id or heading begins a line, document
    order, deduplicated, always including 0 (so any preamble before the
    first rule/heading becomes its own leading segment rather than being
    dropped)."""
    positions = {0}
    for regex in (_RULE_ID_RE, _HEADING_RE):
        for m in regex.finditer(text):
            if _is_line_initial(text, m.start()):
                positions.add(m.start())
    return sorted(positions)


def chunk_text_structure(
    doc_name: str,
    text: str,
    *,
    max_chars: int = MAX_STRUCTURE_CHUNK_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    if not text:
        return []

    boundaries = _structural_boundaries(text)
    segment_bounds = list(zip(boundaries, boundaries[1:] + [len(text)]))

    chunks: list[Chunk] = []
    ordinal = 0
    for seg_start, seg_end in segment_bounds:
        if seg_end <= seg_start:
            continue  # two boundaries can coincide (e.g. a heading immediately followed by a rule id)

        if seg_end - seg_start <= max_chars:
            chunks.append(
                Chunk(doc=doc_name, ordinal=ordinal, char_start=seg_start, char_end=seg_end, text=text[seg_start:seg_end])
            )
            ordinal += 1
            continue

        # Oversized segment: fall back to fixed-size windowing over just
        # this segment's text, then offset each sub-chunk's span back into
        # whole-document coordinates.
        for sub in chunk_text(doc_name, text[seg_start:seg_end], size=max_chars, overlap=overlap):
            chunks.append(
                Chunk(
                    doc=doc_name,
                    ordinal=ordinal,
                    char_start=seg_start + sub.char_start,
                    char_end=seg_start + sub.char_end,
                    text=sub.text,
                )
            )
            ordinal += 1

    return chunks
