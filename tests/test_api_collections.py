"""GET /api/collections -- reads config, no membership logic of its own."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import make_app


def test_lists_configured_collections(tmp_path):
    client = TestClient(make_app(tmp_path, collections={"rules": ["a.md"], "everything": ["a.md", "b.md"]}))

    response = client.get("/api/collections")

    assert response.status_code == 200
    body = response.json()
    assert {"name": "rules", "documents": ["a.md"]} in body
    assert {"name": "everything", "documents": ["a.md", "b.md"]} in body
