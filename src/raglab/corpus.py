"""Corpus loading: enumerate source files, sha256-hash their raw bytes.

Hashing source bytes (not extracted text) is what lets a binary format like
PDF share the same identity mechanism as plain text, and keeps the hash
independent of parser behavior — parser identity is recorded separately
(see `parsers/registry.py`) so a parser upgrade is a loud, detectable event
rather than a silent shift in every downstream character span.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_SUFFIXES = (".txt", ".md", ".pdf")


@dataclass(frozen=True)
class Document:
    name: str
    path: Path
    sha256: str


def hash_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def load_document(path: Path) -> Document:
    if path.suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported corpus file type {path.suffix!r} for {path}")
    return Document(name=path.name, path=path, sha256=hash_bytes(path.read_bytes()))


def load_corpus(corpus_dir: Path) -> dict[str, Document]:
    documents: dict[str, Document] = {}
    for path in sorted(corpus_dir.iterdir()):
        if path.is_file() and path.suffix in SUPPORTED_SUFFIXES:
            documents[path.name] = load_document(path)
    return documents
