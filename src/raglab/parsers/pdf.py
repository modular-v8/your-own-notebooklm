"""PDF text extraction via pymupdf.

`xberg` was tried first per the plan and installed cleanly, but its surface
area (OCR, translation, redaction, email/spreadsheet extraction, ...) is
enormous for a project whose constraint is minimal dependencies — a strong
signal it's the wrong tool for "extract text from a PDF". `pymupdf` is the
plan's own named fallback and does exactly this, nothing more.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from .base import ParserIdentity

# Pages are joined with a blank line so per-line offsets stay well-defined
# and monotonic across page breaks, the same way paragraphs are separated
# within a page.
PAGE_SEPARATOR = "\n\n"


class PdfParser:
    identity = ParserIdentity(name="pymupdf", version=pymupdf.pymupdf_version)

    def extract(self, path: Path) -> str:
        with pymupdf.open(path) as doc:
            pages = [page.get_text() for page in doc]
        return PAGE_SEPARATOR.join(pages)
