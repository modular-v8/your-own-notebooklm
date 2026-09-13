"""CollectionRegistry: merging config.toml's reserved collections with
collections.json's editable ones, and the amendment's rule that a reserved
name is refused identically to a nonexistent one everywhere except
`create`."""

from __future__ import annotations

import pytest

from raglab.collections import (
    CollectionNameConflictError,
    CollectionNotFoundError,
    CollectionRegistry,
    UserCollectionStore,
)

RESERVED = {"rules": ["fb_rules.pdf"], "everything": ["fb_rules.pdf", "amg_mct.md"]}


def make_registry(tmp_path, reserved=None) -> CollectionRegistry:
    store = UserCollectionStore(tmp_path / "collections.json")
    return CollectionRegistry(reserved if reserved is not None else dict(RESERVED), store)


def test_all_merges_reserved_and_editable(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("my-notes", ["a.md"])

    merged = registry.all()

    assert merged["rules"] == ["fb_rules.pdf"]
    assert merged["my-notes"] == ["a.md"]


def test_user_excludes_reserved(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("my-notes", ["a.md"])

    user = registry.user()

    assert user == {"my-notes": ["a.md"]}
    assert "rules" not in user


def test_reserved_returns_config_toml_names(tmp_path):
    registry = make_registry(tmp_path)

    assert registry.reserved() == {"rules", "everything"}


def test_list_summary_shows_only_editable(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("my-notes", ["a.md"])

    summary = {row["name"]: row for row in registry.list_summary()}

    assert "rules" not in summary
    assert "everything" not in summary
    assert summary["my-notes"] == {"name": "my-notes", "document_count": 1}


def test_create_rejects_reserved_name(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(CollectionNameConflictError):
        registry.create("rules")


def test_create_rejects_duplicate_editable_name(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("my-notes")
    with pytest.raises(CollectionNameConflictError):
        registry.create("my-notes")


def test_rename_reserved_collection_raises_not_found(tmp_path):
    # Not LockedCollectionError -- a reserved name looks exactly like one
    # that never existed to every route except create (spec amendment).
    registry = make_registry(tmp_path)
    with pytest.raises(CollectionNotFoundError):
        registry.rename("rules", "renamed-rules")


def test_delete_reserved_collection_raises_not_found(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(CollectionNotFoundError):
        registry.delete("rules")


def test_rename_missing_editable_collection_raises(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(CollectionNotFoundError):
        registry.rename("nonexistent", "new-name")


def test_rename_to_reserved_name_is_a_conflict(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("my-notes")
    with pytest.raises(CollectionNameConflictError):
        registry.rename("my-notes", "rules")


def test_rename_persists_across_new_registry_instance(tmp_path):
    store = UserCollectionStore(tmp_path / "collections.json")
    registry = CollectionRegistry(dict(RESERVED), store)
    registry.create("my-notes", ["a.md"])
    registry.rename("my-notes", "renamed-notes")

    reloaded = CollectionRegistry(dict(RESERVED), UserCollectionStore(tmp_path / "collections.json"))
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


def test_add_document_to_reserved_collection_raises_not_found(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(CollectionNotFoundError):
        registry.add_document("rules", "new.md")


def test_collections_for_never_reports_reserved_membership(tmp_path):
    # collections_for() is what GET /api/documents reports -- an eval-corpus
    # document must never show a reserved collection in its membership list.
    registry = make_registry(tmp_path)
    registry.create("my-notes", ["fb_rules.pdf"])

    assert registry.collections_for("fb_rules.pdf") == ["my-notes"]  # not also "rules"/"everything"


def test_remove_document_everywhere_only_touches_editable(tmp_path):
    registry = make_registry(tmp_path)
    registry.create("notes-a", ["shared.md"])
    registry.create("notes-b", ["shared.md", "other.md"])

    registry.remove_document_everywhere("shared.md")

    merged = registry.all()
    assert merged["notes-a"] == []
    assert merged["notes-b"] == ["other.md"]
    # reserved collections are untouched by construction (they can never
    # reference an uploaded doc), asserted here for completeness
    assert merged["rules"] == ["fb_rules.pdf"]
