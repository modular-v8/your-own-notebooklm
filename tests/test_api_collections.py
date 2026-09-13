"""Collection CRUD. `config.toml`'s reserved collections never reach the
API -- every route (except `create`'s name check) reads and writes through
`user()` only, so a reserved name is refused exactly like a nonexistent one
(spec amendment, 2026-09-13)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import make_app


def test_lists_only_user_collections(tmp_path):
    client = TestClient(
        make_app(tmp_path, collections={"rules": ["a.md"], "everything": ["a.md", "b.md"]}, user_collections={})
    )
    client.post("/api/collections", json={"name": "my-notes"})

    response = client.get("/api/collections")

    assert response.status_code == 200
    assert response.json() == [{"name": "my-notes", "document_count": 0}]


def test_create_collection(tmp_path):
    client = TestClient(make_app(tmp_path, user_collections={}))

    response = client.post("/api/collections", json={"name": "my-notes"})

    assert response.status_code == 201
    names = {c["name"]: c for c in client.get("/api/collections").json()}
    assert names["my-notes"] == {"name": "my-notes", "document_count": 0}


def test_create_collection_rejects_reserved_name_without_saying_why(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))

    response = client.post("/api/collections", json={"name": "rules"})

    assert response.status_code == 409
    detail = response.json()["detail"].lower()
    assert "locked" not in detail
    assert "config.toml" not in detail
    assert "reserved" not in detail  # doesn't reveal *why* it's taken either


def test_rename_reserved_collection_is_404_not_403(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))

    response = client.patch("/api/collections/rules", json={"name": "renamed"})

    assert response.status_code == 404


def test_delete_reserved_collection_is_404_not_403(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))

    response = client.delete("/api/collections/rules")

    assert response.status_code == 404


def test_rename_editable_collection(tmp_path):
    client = TestClient(make_app(tmp_path, user_collections={}))
    client.post("/api/collections", json={"name": "my-notes"})

    response = client.patch("/api/collections/my-notes", json={"name": "renamed-notes"})

    assert response.status_code == 200
    names = {c["name"] for c in client.get("/api/collections").json()}
    assert "renamed-notes" in names
    assert "my-notes" not in names


def test_delete_editable_collection(tmp_path):
    client = TestClient(make_app(tmp_path, user_collections={}))
    client.post("/api/collections", json={"name": "my-notes"})

    response = client.delete("/api/collections/my-notes")

    assert response.status_code == 204
    names = {c["name"] for c in client.get("/api/collections").json()}
    assert "my-notes" not in names


def test_delete_unknown_editable_collection_is_404(tmp_path):
    client = TestClient(make_app(tmp_path, user_collections={}))

    response = client.delete("/api/collections/nonexistent")

    assert response.status_code == 404
