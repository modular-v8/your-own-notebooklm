"""Corpus loading: plain .txt/.md files, sha256-hashed at load time.

Hashes are compared against the gold set's recorded values so an edited
corpus file after gold-set authoring is caught before any model call.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_SUFFIXES = (".txt", ".md")


@dataclass(frozen=True)
class Document:
    name: str
    path: Path
    text: str
    sha256: str


def hash_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def load_document(path: Path) -> Document:
    if path.suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported corpus file type {path.suffix!r} for {path}")
    text = path.read_text(encoding="utf-8")
    return Document(name=path.name, path=path, text=text, sha256=hash_text(text))


def load_corpus(corpus_dir: Path) -> dict[str, Document]:
    documents: dict[str, Document] = {}
    for path in sorted(corpus_dir.iterdir()):
        if path.is_file() and path.suffix in SUPPORTED_SUFFIXES:
            documents[path.name] = load_document(path)
    return documents
