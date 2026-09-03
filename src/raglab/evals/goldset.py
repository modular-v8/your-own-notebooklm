"""Gold-set schema, loader, and validator.

Pydantic v2 collects every field error across every entry in a single
`model_validate` call, which is what lets `load_gold_set` report every
invalid entry in one pass rather than stopping at the first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..corpus import Document

NOT_IN_DOCUMENT_TAG = "not-in-document"


class AnswerLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["line_range", "char_span", "section"]
    start: int | None = None
    end: int | None = None
    name: str | None = None

    @model_validator(mode="after")
    def check_fields_for_type(self) -> AnswerLocation:
        if self.type in ("line_range", "char_span"):
            if self.start is None or self.end is None:
                raise ValueError(f"{self.type} requires start and end")
        elif self.type == "section" and not self.name:
            raise ValueError("section requires name")
        return self


class GoldEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    expected_answer: str | None
    doc: str
    answer_location: AnswerLocation | None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_not_in_document_consistency(self) -> GoldEntry:
        not_in_doc = NOT_IN_DOCUMENT_TAG in self.tags
        if not_in_doc:
            if self.answer_location is not None:
                raise ValueError(f"entry {self.id!r}: tagged {NOT_IN_DOCUMENT_TAG!r} but has answer_location")
            if self.expected_answer is not None:
                raise ValueError(f"entry {self.id!r}: tagged {NOT_IN_DOCUMENT_TAG!r} but has expected_answer")
        else:
            if self.answer_location is None:
                raise ValueError(
                    f"entry {self.id!r}: missing answer_location (or tag as {NOT_IN_DOCUMENT_TAG!r})"
                )
            if self.expected_answer is None:
                raise ValueError(
                    f"entry {self.id!r}: missing expected_answer (or tag as {NOT_IN_DOCUMENT_TAG!r})"
                )
        return self


class GoldSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    corpus_hashes: dict[str, str]
    entries: list[GoldEntry]

    @model_validator(mode="after")
    def check_unique_ids(self) -> GoldSet:
        seen: set[str] = set()
        dupes: set[str] = set()
        for entry in self.entries:
            if entry.id in seen:
                dupes.add(entry.id)
            seen.add(entry.id)
        if dupes:
            raise ValueError(f"duplicate entry ids: {sorted(dupes)}")
        return self

    @model_validator(mode="after")
    def check_docs_referenced(self) -> GoldSet:
        unknown = {e.doc for e in self.entries if e.doc not in self.corpus_hashes}
        if unknown:
            raise ValueError(f"entries reference docs missing from corpus_hashes: {sorted(unknown)}")
        return self


class GoldSetError(Exception):
    """Aggregates every gold-set problem found in one pass."""

    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("\n".join(messages))


def load_gold_set(path: Path) -> GoldSet:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        return GoldSet.model_validate(raw)
    except ValidationError as exc:
        messages = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise GoldSetError(messages) from exc


class CorpusMismatchError(Exception):
    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("\n".join(messages))


def verify_corpus_hashes(gold: GoldSet, documents: dict[str, Document]) -> None:
    problems = []
    for name, expected_hash in gold.corpus_hashes.items():
        doc = documents.get(name)
        if doc is None:
            problems.append(f"{name}: referenced by gold set but missing from corpus")
        elif doc.sha256 != expected_hash:
            problems.append(
                f"{name}: hash mismatch (gold set expects {expected_hash}, found {doc.sha256})"
            )
    if problems:
        raise CorpusMismatchError(problems)
