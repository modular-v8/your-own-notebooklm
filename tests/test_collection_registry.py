"""CollectionRegistry: merging config.toml's locked collections with
collections.json's editable ones, and locked-name enforcement."""

from __future__ import annotations

import pytest

from raglab.collections import (
    CollectionNameConflictError,
    CollectionNotFoundError,
    CollectionRegistry,
    LockedCollectionError,
    UserCollectionStore,
)

LOCKED = {"rules": ["fb_rules.pdf"], "everything": ["fb_rules.pdf", "amg_mct.md"]}


def make_registry(tmp_path, locked=None) -> CollectionRegistry:
    store = UserCollectionStore(tmp_path / "collections.json")
    return CollectionRegistry(locked if locked is not None else dict(LOCKED), store)


def test_all_merges_locked_and_editable(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("my-notes", ["a.md"])

    merged = registry.all()

    assert merged["rules"] == ["fb_rules.pdf"]
    assert merged["my-notes"] == ["a.md"]


def test_list_summary_flags_locked_vs_editable(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("my-notes", ["a.md"])

    summary = {row["name"]: row for row in registry.list_summary()}

    assert summary["rules"]["locked"] is True
    assert summary["rules"]["document_count"] == 1
    assert summary["my-notes"]["locked"] is False
    assert summary["my-notes"]["document_count"] == 1


def test_create_rejects_locked_name(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(CollectionNameConflictError):
        registry.create("rules")


def test_create_rejects_duplicate_editable_name(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("my-notes")
    with pytest.raises(CollectionNameConflictError):
        registry.create("my-notes")


def test_rename_locked_collection_raises(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(LockedCollectionError):
        registry.rename("rules", "renamed-rules")


def test_delete_locked_collection_raises(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(LockedCollectionError):
        registry.delete("rules")


def test_rename_missing_editable_collection_raises(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(CollectionNotFoundError):
        registry.rename("nonexistent", "new-name")


def test_rename_persists_across_new_registry_instance(tmp_path):
    store = UserCollectionStore(tmp_path / "collections.json")
    registry = CollectionRegistry(dict(LOCKED), store)
    registry.create("my-notes", ["a.md"])
    registry.rename("my-notes", "renamed-notes")

    reloaded = CollectionRegistry(dict(LOCKED), UserCollectionStore(tmp_path / "collections.json"))
    assert reloaded.all()["renamed-notes"] == ["a.md"]
    assert "my-notes" not in reloaded.all()


def test_delete_editable_collection_leaves_documents_on_disk_conceptually(tmp_path):
    # delete() only touches collections.json -- it has no filesystem side
    # effect on documents, which is the point (spec: documents survive).
    registry = make_registry(tmp_path)
    registry.create("my-notes", ["a.md"])
    registry.delete("my-notes")

    assert "my-notes" not in registry.all()


def test_add_and_remove_document_membership(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("my-notes")
    registry.add_document("my-notes", "a.md")
    assert registry.all()["my-notes"] == ["a.md"]

    registry.remove_document("my-notes", "a.md")
    assert registry.all()["my-notes"] == []


def test_add_document_to_locked_collection_raises(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(LockedCollectionError):
        registry.add_document("rules", "new.md")


def test_remove_document_everywhere_only_touches_editable(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("notes-a", ["shared.md"])
    registry.create("notes-b", ["shared.md", "other.md"])

    registry.remove_document_everywhere("shared.md")

    merged = registry.all()
    assert merged["notes-a"] == []
    assert merged["notes-b"] == ["other.md"]
    # locked collections are untouched by construction (they can never
    # reference an uploaded doc), asserted here for completeness
    assert merged["rules"] == ["fb_rules.pdf"]
