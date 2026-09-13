"""Collection membership: which documents belong to which named collections.

Membership for the collections named in `config.toml` ("reserved" names,
kept for the CLI eval harness) is resolved once at index time (chunk-level
`collections` field) and again whenever a search or eval run names the
collection it's scoped to. Retrieval still never filters to a single
document (Phase 1 decision, carried forward) -- a collection is the coarser
unit Phase 3 introduced instead.

Phase 8 adds a second, writable source: `collections.json`, holding
user-created collections the app can create, rename, delete, and edit the
membership of. Phase 8's amendment (2026-09-13) hides `config.toml`'s
collections from the application entirely -- a person using the web app has
no reason to see this project's test fixtures. `CollectionRegistry` exposes
three views over the same data: `all()` (merged, unchanged shape, for the
CLI and for tagging chunks at build time), `user()` (editable only -- every
API route uses this and only this), and `reserved()` (the names `create`
alone needs to reject, without saying why).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class UnknownCollectionError(Exception):
    """Raised naming both the requested collection and the ones that
    actually exist -- spec: abort naming both."""

    def __init__(self, name: str, known: list[str]):
        self.name = name
        self.known = known
        super().__init__(f"collection {name!r} not found in config.toml (known: {known})")


class CollectionNameConflictError(Exception):
    """Raised when a create would collide with an existing name, editable or
    reserved -- the message never says which, so a reserved name isn't
    distinguishable from an ordinary conflict (spec: doesn't reveal why)."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"collection {name!r} already exists")


class CollectionNotFoundError(Exception):
    """Raised for any mutation targeting a name absent from `user()` --
    including a `config.toml` name, which must be indistinguishable from one
    that never existed at all (spec: refused identically to nonexistent)."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"collection {name!r} not found")


def require_collection(name: str, collections: dict[str, list[str]]) -> list[str]:
    """The document list for `name`, or raise UnknownCollectionError."""
    if name not in collections:
        raise UnknownCollectionError(name, sorted(collections))
    return collections[name]


def collections_for_doc(doc: str, collections: dict[str, list[str]]) -> list[str]:
    """Every collection `doc` is a member of, in config declaration order."""
    return [name for name, docs in collections.items() if doc in docs]


def unreachable_documents(doc_names: list[str], collections: dict[str, list[str]]) -> list[str]:
    """Corpus documents that belong to no collection -- indexed but
    unreachable by any scoped query (spec: unwanted-behavior)."""
    member_docs = {doc for docs in collections.values() for doc in docs}
    return sorted(name for name in doc_names if name not in member_docs)


USER_COLLECTIONS_VERSION = 1


@dataclass
class UserCollectionStore:
    """Reads and writes `collections.json` -- the writable mirror of
    `config.toml`'s `[collections]` block. File-per-store, like every other
    piece of state in this project; created lazily on first write so a
    fresh clone needs no extra setup step."""

    path: Path

    def load(self) -> dict[str, list[str]]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {name: list(docs) for name, docs in raw.get("collections", {}).items()}

    def save(self, collections: dict[str, list[str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": USER_COLLECTIONS_VERSION, "collections": collections}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class CollectionRegistry:
    """Merges `config.toml`'s reserved collections with `collections.json`'s
    editable ones. The two never mix on disk (spec: data & integrations).
    No API route ever calls `all()` -- a request naming a reserved
    collection finds nothing in `user()` and is refused exactly as a
    nonexistent one would be, with no special case needed."""

    def __init__(self, locked: dict[str, list[str]], store: UserCollectionStore):
        self._reserved = {name: list(docs) for name, docs in locked.items()}
        self._store = store

    def reserved(self) -> set[str]:
        return set(self._reserved)

    def all(self) -> dict[str, list[str]]:
        """Merged view in the exact shape the CLI eval harness and build-time
        chunk tagging expect. Never used by an API route."""
        merged = dict(self._reserved)
        merged.update(self._store.load())
        return merged

    def user(self) -> dict[str, list[str]]:
        """Editable collections only -- every API route reads and writes
        through this view, never `all()`."""
        return self._store.load()

    def list_summary(self) -> list[dict]:
        return [{"name": name, "document_count": len(docs)} for name, docs in self.user().items()]

    def collections_for(self, doc: str) -> list[str]:
        """A document's *user*-visible collections only -- an eval-corpus
        document reported here would leak a fixture the app never lists."""
        return collections_for_doc(doc, self.user())

    def create(self, name: str, docs: list[str] | None = None) -> None:
        if name in self._reserved:
            raise CollectionNameConflictError(name)
        editable = self._store.load()
        if name in editable:
            raise CollectionNameConflictError(name)
        editable[name] = list(docs or [])
        self._store.save(editable)

    def rename(self, name: str, new_name: str) -> None:
        editable = self._store.load()
        if name not in editable:
            raise CollectionNotFoundError(name)
        if new_name in self._reserved or new_name in editable:
            raise CollectionNameConflictError(new_name)
        editable[new_name] = editable.pop(name)
        self._store.save(editable)

    def delete(self, name: str) -> None:
        editable = self._store.load()
        if name not in editable:
            raise CollectionNotFoundError(name)
        del editable[name]
        self._store.save(editable)

    def add_document(self, name: str, doc: str) -> None:
        editable = self._store.load()
        if name not in editable:
            raise CollectionNotFoundError(name)
        if doc not in editable[name]:
            editable[name].append(doc)
            self._store.save(editable)

    def remove_document(self, name: str, doc: str) -> None:
        editable = self._store.load()
        if name not in editable:
            raise CollectionNotFoundError(name)
        if doc in editable[name]:
            editable[name].remove(doc)
            self._store.save(editable)

    def remove_document_everywhere(self, doc: str) -> None:
        """Used only when a document is deleted from disk -- membership in
        every *editable* collection is dropped; a reserved collection cannot
        reference an uploaded document in the first place."""
        editable = self._store.load()
        changed = False
        for docs in editable.values():
            if doc in docs:
                docs.remove(doc)
                changed = True
        if changed:
            self._store.save(editable)
