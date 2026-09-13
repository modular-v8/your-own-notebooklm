"""Collection membership: which documents belong to which named collections.

Membership for the collections named in `config.toml` ("locked" collections)
is resolved once at index time (chunk-level `collections` field) and again
whenever a search or eval run names the collection it's scoped to. Retrieval
still never filters to a single document (Phase 1 decision, carried
forward) -- a collection is the coarser unit Phase 3 introduced instead.

Phase 8 adds a second, writable source: `collections.json`, holding
user-created collections the app can create, rename, delete, and edit the
membership of. `CollectionRegistry` merges the two into the same
`dict[str, list[str]]` shape every existing caller (`require_collection`,
the retriever, the eval runner) already consumes, so none of them change --
only the API layer needs to know which names are locked.
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


class LockedCollectionError(Exception):
    """Raised whenever a mutation targets a collection defined in
    config.toml. Enforced here, not in the UI -- anything reachable by curl
    is reachable by accident (spec: users & context)."""

    def __init__(self, name: str, action: str):
        self.name = name
        self.action = action
        super().__init__(f"collection {name!r} is locked (defined in config.toml) and cannot be {action}")


class CollectionNameConflictError(Exception):
    """Raised when a create/rename would collide with an existing name,
    locked or editable -- both namespaces share one flat name-space."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"collection {name!r} already exists")


class CollectionNotFoundError(Exception):
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
    """Merges `config.toml`'s locked collections with `collections.json`'s
    editable ones. The two never mix on disk (spec: data & integrations) --
    a locked name is simply never writable, checked before every mutation
    below rather than trusted to a caller."""

    def __init__(self, locked: dict[str, list[str]], store: UserCollectionStore):
        self._locked = {name: list(docs) for name, docs in locked.items()}
        self._store = store

    @property
    def locked_names(self) -> set[str]:
        return set(self._locked)

    def all(self) -> dict[str, list[str]]:
        """Merged view in the exact shape every pre-Phase-8 caller expects."""
        merged = dict(self._locked)
        merged.update(self._store.load())
        return merged

    def list_summary(self) -> list[dict]:
        merged_editable = self._store.load()
        summary = [
            {"name": name, "locked": True, "document_count": len(docs)} for name, docs in self._locked.items()
        ]
        summary.extend(
            {"name": name, "locked": False, "document_count": len(docs)}
            for name, docs in merged_editable.items()
        )
        return summary

    def collections_for(self, doc: str) -> list[str]:
        return collections_for_doc(doc, self.all())

    def _require_unlocked(self, name: str, action: str) -> dict[str, list[str]]:
        if name in self._locked:
            raise LockedCollectionError(name, action)
        return self._store.load()

    def create(self, name: str, docs: list[str] | None = None) -> None:
        if name in self._locked:
            raise CollectionNameConflictError(name)
        editable = self._store.load()
        if name in editable:
            raise CollectionNameConflictError(name)
        editable[name] = list(docs or [])
        self._store.save(editable)

    def rename(self, name: str, new_name: str) -> None:
        editable = self._require_unlocked(name, "renamed")
        if name not in editable:
            raise CollectionNotFoundError(name)
        if new_name in self._locked or new_name in editable:
            raise CollectionNameConflictError(new_name)
        editable[new_name] = editable.pop(name)
        self._store.save(editable)

    def delete(self, name: str) -> None:
        editable = self._require_unlocked(name, "deleted")
        if name not in editable:
            raise CollectionNotFoundError(name)
        del editable[name]
        self._store.save(editable)

    def add_document(self, name: str, doc: str) -> None:
        editable = self._require_unlocked(name, "modified")
        if name not in editable:
            raise CollectionNotFoundError(name)
        if doc not in editable[name]:
            editable[name].append(doc)
            self._store.save(editable)

    def remove_document(self, name: str, doc: str) -> None:
        editable = self._require_unlocked(name, "modified")
        if name not in editable:
            raise CollectionNotFoundError(name)
        if doc in editable[name]:
            editable[name].remove(doc)
            self._store.save(editable)

    def remove_document_everywhere(self, doc: str) -> None:
        """Used only when a document is deleted from disk -- membership in
        every *editable* collection is dropped; locked collections cannot
        reference an uploaded document in the first place."""
        editable = self._store.load()
        changed = False
        for docs in editable.values():
            if doc in docs:
                docs.remove(doc)
                changed = True
        if changed:
            self._store.save(editable)
