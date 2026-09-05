"""Suffix -> parser lookup; wraps extraction with the document's identity."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..corpus import Document
from .base import Parser, ParserIdentity
from .pdf import PdfParser
from .text import TextParser

_PARSERS: dict[str, Parser] = {
    ".txt": TextParser(),
    ".md": TextParser(),
    ".pdf": PdfParser(),
}


def parser_for(path: Path) -> Parser:
    parser = _PARSERS.get(path.suffix)
    if parser is None:
        raise ValueError(f"no parser registered for suffix {path.suffix!r} ({path})")
    return parser


@dataclass(frozen=True)
class ExtractedDocument:
    document: Document
    parser: ParserIdentity
    text: str


class ParserError(RuntimeError):
    def __init__(self, doc_name: str, message: str):
        self.doc_name = doc_name
        super().__init__(f"{doc_name}: {message}")


def extract_document(document: Document) -> ExtractedDocument:
    parser = parser_for(document.path)
    try:
        text = parser.extract(document.path)
    except Exception as exc:  # parser failure is a per-document, recorded event, not a crash
        raise ParserError(document.name, str(exc)) from exc
    return ExtractedDocument(document=document, parser=parser.identity, text=text)
