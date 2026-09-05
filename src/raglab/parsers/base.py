"""Parser protocol: extracted text plus a recorded parser identity.

Parser identity is part of a document's identity (see `spec.md`): if a
parser upgrade shifts extraction by even one character, every gold
`answer_location` and every stored chunk span silently points at the wrong
place. Recording `name`/`version` alongside the source hash turns that into
a loud, detectable mismatch instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ParserIdentity:
    name: str
    version: str

    def __str__(self) -> str:
        return f"{self.name}/{self.version}"


@runtime_checkable
class Parser(Protocol):
    identity: ParserIdentity

    def extract(self, path: Path) -> str: ...
