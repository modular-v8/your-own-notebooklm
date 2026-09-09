"""GET /api/chunks/{chunk_id} -- char span -> line range, computed at
request time from the source document's extracted text."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import CHUNK_ID, CHUNK_TEXT, DOC_NAME, make_app


def test_resolves_known_chunk_to_text_and_line_range(tmp_path):
    client = TestClient(make_app(tmp_path))

    response = client.get(f"/api/chunks/{CHUNK_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body == {"chunk_id": CHUNK_ID, "doc": DOC_NAME, "text": CHUNK_TEXT, "line_start": 3, "line_end": 3}


def test_unknown_chunk_id_is_404(tmp_path):
    client = TestClient(make_app(tmp_path))

    response = client.get("/api/chunks/doc.md:9999")

    assert response.status_code == 404
