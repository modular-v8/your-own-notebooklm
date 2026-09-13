"""Collection CRUD -- locked collections (config.toml) refused at the API,
editable ones (collections.json) create/rename/delete."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import make_app


def test_lists_configured_collections(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"], "everything": ["a.md", "b.md"]}))

    response = client.get("/api/collections")

    assert response.status_code == 200
    body = response.json()
    assert {"name": "rules", "locked": True, "document_count": 1} in body
    assert {"name": "everything", "locked": True, "document_count": 2} in body


def test_create_collection(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))

    response = client.post("/api/collections", json={"name": "my-notes"})

    assert response.status_code == 201
    names = {c["name"]: c for c in client.get("/api/collections").json()}
    assert names["my-notes"] == {"name": "my-notes", "locked": False, "document_count": 0}


def test_create_collection_rejects_locked_name(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))

    response = client.post("/api/collections", json={"name": "rules"})

    assert response.status_code == 409


def test_rename_locked_collection_is_refused(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))

    response = client.patch("/api/collections/rules", json={"name": "renamed"})

    assert response.status_code == 403
    assert "rules" in response.json()["detail"]


def test_delete_locked_collection_is_refused(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))

    response = client.delete("/api/collections/rules")

    assert response.status_code == 403


def test_rename_editable_collection(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))
    client.post("/api/collections", json={"name": "my-notes"})

    response = client.patch("/api/collections/my-notes", json={"name": "renamed-notes"})

    assert response.status_code == 200
    names = {c["name"] for c in client.get("/api/collections").json()}
    assert "renamed-notes" in names
    assert "my-notes" not in names


def test_delete_editable_collection(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))
    client.post("/api/collections", json={"name": "my-notes"})

    response = client.delete("/api/collections/my-notes")

    assert response.status_code == 204
    names = {c["name"] for c in client.get("/api/collections").json()}
    assert "my-notes" not in names


def test_delete_unknown_editable_collection_is_404(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"]}))

    response = client.delete("/api/collections/nonexistent")

    assert response.status_code == 404
