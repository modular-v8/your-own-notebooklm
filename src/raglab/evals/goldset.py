"""Gold-set schema, loader, and validator.

Pydantic v2 collects every field error across every entry in a single
`model_validate` call, which is what lets `load_gold_set` report every
invalid entry in one pass rather than stopping at the first.

Schema v3 replaces the single `question` string with a `turns` list, so an
entry can carry conversation history: every turn but the last is a scripted
prior exchange (question + answer), and the last is the one actually
retrieved for and graded. A gold set also names the `collection` its
entries run against (specs/3-collections/spec.md). v1 and v2 files are
rejected outright, named, with the migration pointed at -- not silently
reinterpreted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..corpus import Document

NOT_IN_DOCUMENT_TAG = "not-in-document"
NOT_IN_COLLECTION_TAG = "not-in-collection"
FOLLOW_UP_TAG = "follow-up"

# Controlled tag vocabulary (spec: "a controlled tag vocabulary, with
# per-tag metric breakdowns"). Free-form additional tags are permitted --
# an entry missing every one of these is a validation *warning*, not an
# error, since Phase 4's per-tag breakdown is what actually needs it.
TAG_VOCABULARY = frozenset(
    {
        "lexical-anchor",
        "vocabulary-mismatch",
        "synthesis",
        "near-duplicate",
        "boundary-spanning",
        "cross-document",
        NOT_IN_DOCUMENT_TAG,
        FOLLOW_UP_TAG,
        NOT_IN_COLLECTION_TAG,
    }
)

V1_REJECTION_MESSAGE = (
    "gold-set schema v1 is no longer supported: `doc` + `answer_location` "
    "were replaced by a `sources` list (specs/2-grounded-answering/spec.md). "
    "Migrate this file (see scripts/migrate_goldsets_v2.py for the mechanical "
    "shape) before loading it."
)

V2_REJECTION_MESSAGE = (
    "gold-set schema v2 is no longer supported: `question` was replaced by a "
    "`turns` list, and a gold set now names a `collection` "
    "(specs/3-collections/spec.md). Migrate this file (see "
    "scripts/migrate_goldsets_v3.py for the mechanical shape) before loading it."
)


class AnswerLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["line_range", "char_span", "section"]
    start: int | None = None
    end: int | None = None
    value: list[str] | None = None
    # Only meaningful for type == "section"; applied per anchor in `value`,
    # not once per answer_location (see plan.md).
    occurrence: Literal["first", "last"] | int | None = None

    @model_validator(mode="after")
    def check_fields_for_type(self) -> AnswerLocation:
        if self.type in ("line_range", "char_span"):
            if self.start is None or self.end is None:
                raise ValueError(f"{self.type} requires start and end")
            if self.occurrence is not None:
                raise ValueError(f"{self.type} does not support occurrence")
        elif self.type == "section":
            if not self.value:
                raise ValueError("section requires value")
            if isinstance(self.occurrence, int) and self.occurrence < 1:
                raise ValueError("occurrence index must be a 1-based positive integer")
        return self


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc: str
    answer_location: AnswerLocation


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    # Required on every turn except the last (see GoldEntry.check_turns).
    answer: str | None = None


class GoldEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    turns: list[Turn] = Field(min_length=1)
    expected_answer: str | None
    sources: list[Source] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @property
    def question(self) -> str:
        """The final turn's question -- the only one retrieval and the
        judge ever see as *the* question. A single-turn entry's only turn."""
        return self.turns[-1].question

    @property
    def history(self) -> list[Turn]:
        """Prior turns, each carrying its scripted answer -- conversation
        context handed to the model. Empty for a standalone entry. Retrieval
        never sees this; see specs/3-collections/plan.md."""
        return self.turns[:-1]

    @property
    def is_follow_up(self) -> bool:
        return len(self.turns) > 1

    @property
    def docs(self) -> list[str]:
        """Unique document names referenced by this entry's sources, in
        first-seen order. Empty for a not-in-document entry."""
        seen: list[str] = []
        for source in self.sources:
            if source.doc not in seen:
                seen.append(source.doc)
        return seen

    @model_validator(mode="after")
    def check_turns(self) -> GoldEntry:
        for turn in self.turns[:-1]:
            if turn.answer is None:
                raise ValueError(
                    f"entry {self.id!r}: prior turn {turn.question!r} is missing its scripted answer"
                )
        if self.turns[-1].answer is not None:
            raise ValueError(f"entry {self.id!r}: the final (graded) turn must not carry a scripted answer")
        return self

    @model_validator(mode="after")
    def check_not_in_document_consistency(self) -> GoldEntry:
        not_in_doc = NOT_IN_DOCUMENT_TAG in self.tags
        empty_sources = len(self.sources) == 0
        if not_in_doc != empty_sources:
            raise ValueError(
                f"entry {self.id!r}: `sources: []` and the {NOT_IN_DOCUMENT_TAG!r} tag "
                "must imply each other"
            )
        if not_in_doc:
            if self.expected_answer is not None:
                raise ValueError(f"entry {self.id!r}: tagged {NOT_IN_DOCUMENT_TAG!r} but has expected_answer")
        else:
            if self.expected_answer is None:
                raise ValueError(
                    f"entry {self.id!r}: missing expected_answer (or tag as {NOT_IN_DOCUMENT_TAG!r})"
                )
        return self


class GoldSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[3]
    collection: str
    corpus_hashes: dict[str, str]
    entries: list[GoldEntry]

    @property
    def primary_doc(self) -> str | None:
        """The document most entries' sources reference -- used as the
        implicit whole-doc target for not-in-document entries, which name
        no document of their own. Ties broken by corpus_hashes order."""
        counts: dict[str, int] = {}
        for entry in self.entries:
            for source in entry.sources:
                counts[source.doc] = counts.get(source.doc, 0) + 1
        if not counts:
            # No entry names a document at all (e.g. every entry is
            # not-in-document) -- fall back to the corpus's own first doc.
            return next(iter(self.corpus_hashes), None)
        best_doc, best_count = None, -1
        for doc in self.corpus_hashes:
            count = counts.get(doc, 0)
            if count > best_count:
                best_doc, best_count = doc, count
        return best_doc

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
        unknown = {
            source.doc
            for entry in self.entries
            for source in entry.sources
            if source.doc not in self.corpus_hashes
        }
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
    if isinstance(raw, dict) and raw.get("version") == 1:
        raise GoldSetError([f"{path}: {V1_REJECTION_MESSAGE}"])
    if isinstance(raw, dict) and raw.get("version") == 2:
        raise GoldSetError([f"{path}: {V2_REJECTION_MESSAGE}"])
    try:
        return GoldSet.model_validate(raw)
    except ValidationError as exc:
        messages = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise GoldSetError(messages) from exc


def check_tag_vocabulary(gold: GoldSet) -> list[str]:
    """Entries carrying no tag from TAG_VOCABULARY -- a warning, not an
    error, since they're still runnable, just invisible in the per-tag
    breakdown."""
    return [
        f"{entry.id}: no tag from the controlled vocabulary ({sorted(TAG_VOCABULARY)})"
        for entry in gold.entries
        if not any(tag in TAG_VOCABULARY for tag in entry.tags)
    ]


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


class CollectionMembershipError(Exception):
    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("\n".join(messages))


def verify_collection_membership(gold: GoldSet, collections: dict[str, list[str]]) -> None:
    """Every entry's source doc(s) must belong to the gold set's own
    declared collection, unless the entry is tagged not-in-collection --
    the whole point of that tag is to cite a doc deliberately outside the
    active scope (spec: unwanted-behavior)."""
    if gold.collection not in collections:
        raise CollectionMembershipError(
            [f"collection {gold.collection!r} not found in config.toml (known: {sorted(collections)})"]
        )
    member_docs = set(collections[gold.collection])
    problems = []
    for entry in gold.entries:
        if NOT_IN_COLLECTION_TAG in entry.tags:
            continue
        outside = sorted(set(entry.docs) - member_docs)
        if outside:
            problems.append(f"{entry.id}: doc(s) {outside} not in collection {gold.collection!r}")
    if problems:
        raise CollectionMembershipError(problems)
