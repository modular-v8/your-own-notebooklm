"""Collection membership resolution and the unreachable-document warning."""

from __future__ import annotations

import pytest

from raglab.collections import (
    UnknownCollectionError,
    collections_for_doc,
    require_collection,
    unreachable_documents,
)
from raglab.evals.goldset import CollectionMembershipError, GoldEntry, GoldSet, Source, Turn, verify_collection_membership
from raglab.evals.goldset import AnswerLocation

COLLECTIONS = {
    "rules": ["fb_rules.pdf"],
    "transmissions": ["amg_mct.md", "egear.md"],
    "everything": ["fb_rules.pdf", "amg_mct.md", "egear.md"],
}


def test_collections_for_doc_returns_every_membership():
    assert collections_for_doc("fb_rules.pdf", COLLECTIONS) == ["rules", "everything"]
    assert collections_for_doc("amg_mct.md", COLLECTIONS) == ["transmissions", "everything"]


def test_collections_for_doc_empty_when_no_membership():
    assert collections_for_doc("orphan.md", COLLECTIONS) == []


def test_require_collection_returns_docs():
    assert require_collection("rules", COLLECTIONS) == ["fb_rules.pdf"]


def test_require_collection_raises_naming_both():
    with pytest.raises(UnknownCollectionError) as exc_info:
        require_collection("nonexistent", COLLECTIONS)
    assert "nonexistent" in str(exc_info.value)
    assert "rules" in str(exc_info.value)  # known collections are named too


def test_unreachable_documents_flags_docs_in_no_collection():
    doc_names = ["fb_rules.pdf", "amg_mct.md", "orphan.md"]
    assert unreachable_documents(doc_names, COLLECTIONS) == ["orphan.md"]


def test_unreachable_documents_empty_when_all_covered():
    doc_names = ["fb_rules.pdf", "amg_mct.md"]
    assert unreachable_documents(doc_names, COLLECTIONS) == []


def _entry(entry_id: str, doc: str, tags: list[str] | None = None) -> GoldEntry:
    return GoldEntry(
        id=entry_id,
        turns=[Turn(question=f"Question for {entry_id}")],
        expected_answer="An answer.",
        sources=[Source(doc=doc, answer_location=AnswerLocation(type="line_range", start=1, end=1))],
        tags=tags or [],
    )


def test_verify_collection_membership_passes_when_docs_in_scope():
    gold = GoldSet(
        version=3,
        collection="transmissions",
        corpus_hashes={"amg_mct.md": "sha256:a", "egear.md": "sha256:b"},
        entries=[_entry("q-001", "amg_mct.md")],
    )
    verify_collection_membership(gold, COLLECTIONS)  # must not raise


def test_verify_collection_membership_rejects_out_of_scope_doc():
    gold = GoldSet(
        version=3,
        collection="rules",
        corpus_hashes={"fb_rules.pdf": "sha256:a", "amg_mct.md": "sha256:b"},
        entries=[_entry("q-001", "amg_mct.md")],
    )
    with pytest.raises(CollectionMembershipError) as exc_info:
        verify_collection_membership(gold, COLLECTIONS)
    assert any("q-001" in message for message in exc_info.value.messages)


def test_verify_collection_membership_allows_out_of_scope_doc_when_tagged():
    """not-in-collection is the escape hatch: a question answerable
    elsewhere in the corpus, deliberately cited outside the active scope."""
    gold = GoldSet(
        version=3,
        collection="rules",
        corpus_hashes={"fb_rules.pdf": "sha256:a", "amg_mct.md": "sha256:b"},
        entries=[_entry("q-001", "amg_mct.md", tags=["not-in-collection"])],
    )
    verify_collection_membership(gold, COLLECTIONS)  # must not raise


def test_verify_collection_membership_rejects_unknown_gold_collection():
    gold = GoldSet(
        version=3,
        collection="nonexistent",
        corpus_hashes={"fb_rules.pdf": "sha256:a"},
        entries=[_entry("q-001", "fb_rules.pdf")],
    )
    with pytest.raises(CollectionMembershipError) as exc_info:
        verify_collection_membership(gold, COLLECTIONS)
    assert any("nonexistent" in message for message in exc_info.value.messages)
