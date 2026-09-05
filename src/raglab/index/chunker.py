"""Fixed-size chunker: char spans preserved, no structure awareness.

900/150 is a recorded default, not a swept parameter — sweeping chunk size
is Phase 4's job and needs this phase's recall@k to already exist to
measure against. 900 chars leaves generous headroom under bge-small's
512-token truncation limit (~2,000 chars).
"""

from __future__ import annotations

from dataclasses import dataclass

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


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
