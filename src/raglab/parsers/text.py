"""Plain .txt/.md passthrough parser."""

from __future__ import annotations

from pathlib import Path

from .base import ParserIdentity

TEXT_PARSER_VERSION = "1"


class TextParser:
    identity = ParserIdentity(name="text", version=TEXT_PARSER_VERSION)

    def extract(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")
