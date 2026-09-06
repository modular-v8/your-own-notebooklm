"""Collection membership: which documents belong to which named collections.

Membership lives in `config.toml`, resolved once at index time (chunk-level
`collections` field) and again whenever a search or eval run names the
collection it's scoped to. Retrieval still never filters to a single
document (Phase 1 decision, carried forward) -- a collection is the
coarser unit this phase introduces instead.
"""

from __future__ import annotations


class UnknownCollectionError(Exception):
    """Raised naming both the requested collection and the ones that
    actually exist -- spec: abort naming both."""

    def __init__(self, name: str, known: list[str]):
        self.name = name
        self.known = known
        super().__init__(f"collection {name!r} not found in config.toml (known: {known})")


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
