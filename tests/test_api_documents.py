"""Document upload, listing, membership removal, and disk deletion.

Upload runs its rebuild in a background task, so these tests use an async
httpx client against the ASGI app directly and poll the job endpoint --
`TestClient`'s synchronous portal gives no reliable way to wait for a
detached `asyncio.create_task` to finish between two separate requests.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.conftest import make_app


async def _poll_job(client: httpx.AsyncClient, job_id: str, *, timeout_s: float = 5.0) -> dict:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while True:
        response = await client.get(f"/api/jobs/{job_id}")
        body = response.json()
        if body["state"] in ("ready", "failed"):
            return body
        if loop.time() > deadline:
            raise AssertionError(f"job {job_id} did not finish in time: {body}")
        await asyncio.sleep(0.01)


def _async_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(tmp_path):
    app = make_app(tmp_path, collections={"rules": ["a.md"]})
    async with _async_client(app) as c:
        yield c


def _minimal_pdf_bytes() -> bytes:
    import fitz  # pymupdf -- already a hard dependency, no new import for tests

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Smoke-test PDF content about widgets.")
    return doc.tobytes()


async def test_upload_md_indexes_and_becomes_ready(client):
    await client.post("/api/collections", json={"name": "notes"})

    response = await client.post(
        "/api/collections/notes/documents",
        files={"file": ("notes.md", b"# Heading\n\nSome markdown content about widgets.", "text/markdown")},
    )

    assert response.status_code == 202
    finished = await _poll_job(client, response.json()["job_id"])
    assert finished["state"] == "ready"


async def test_upload_pdf_indexes_and_becomes_ready(client):
    await client.post("/api/collections", json={"name": "notes"})

    response = await client.post(
        "/api/collections/notes/documents",
        files={"file": ("notes.pdf", _minimal_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 202
    finished = await _poll_job(client, response.json()["job_id"])
    assert finished["state"] == "ready"


async def test_upload_txt_indexes_and_becomes_ready(client):
    await client.post("/api/collections", json={"name": "notes"})

    response = await client.post(
        "/api/collections/notes/documents",
        files={"file": ("notes.txt", b"Some uploaded content about widgets.", "text/plain")},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["doc"] == "notes.txt"

    finished = await _poll_job(client, job["job_id"])
    assert finished["state"] == "ready"
    assert finished["chunk_count"] >= 1

    docs = (await client.get("/api/documents")).json()
    entry = next(d for d in docs if d["name"] == "notes.txt")
    assert entry["state"] == "ready"
    assert entry["collections"] == ["notes"]
    assert entry["locked"] is False


async def test_upload_unsupported_extension_is_rejected_by_name(client):
    await client.post("/api/collections", json={"name": "notes"})

    response = await client.post(
        "/api/collections/notes/documents",
        files={"file": ("notes.exe", b"binary junk", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert ".exe" in response.json()["detail"]


async def test_upload_duplicate_filename_is_rejected(client):
    await client.post("/api/collections", json={"name": "notes"})

    first = await client.post(
        "/api/collections/notes/documents",
        files={"file": ("dup.txt", b"first version", "text/plain")},
    )
    await _poll_job(client, first.json()["job_id"])

    second = await client.post(
        "/api/collections/notes/documents",
        files={"file": ("dup.txt", b"second version", "text/plain")},
    )

    assert second.status_code == 409
    assert "dup.txt" in second.json()["detail"]


async def test_upload_to_locked_collection_is_refused(client):
    response = await client.post(
        "/api/collections/rules/documents",
        files={"file": ("locked-target.txt", b"content", "text/plain")},
    )

    assert response.status_code == 403


async def test_upload_to_unknown_collection_is_404(client):
    response = await client.post(
        "/api/collections/nonexistent/documents",
        files={"file": ("x.txt", b"content", "text/plain")},
    )

    assert response.status_code == 404


async def test_remove_from_collection_keeps_document_in_other_collections(client):
    await client.post("/api/collections", json={"name": "notes-a"})
    await client.post("/api/collections", json={"name": "notes-b"})

    upload = await client.post(
        "/api/collections/notes-a/documents",
        files={"file": ("shared.txt", b"shared content", "text/plain")},
    )
    job = await _poll_job(client, upload.json()["job_id"])
    assert job["state"] == "ready"

    # No separate "add to an existing collection" endpoint exists in this
    # phase's scope; upload targets one collection at a time, so membership
    # beyond that one collection isn't exercised here -- deleting the only
    # collection a doc belongs to is exercised by the disk-delete test below.
    remove = await client.delete("/api/collections/notes-a/documents/shared.txt")
    assert remove.status_code == 204

    docs_after = (await client.get("/api/documents")).json()
    entry_after = next(d for d in docs_after if d["name"] == "shared.txt")
    assert entry_after["collections"] == []
    assert entry_after["state"] == "ready"  # still indexed, just unlisted


async def test_delete_from_disk_warns_then_deletes_with_confirm(client):
    await client.post("/api/collections", json={"name": "notes-a"})
    upload = await client.post(
        "/api/collections/notes-a/documents",
        files={"file": ("to-delete.txt", b"content to delete", "text/plain")},
    )
    await _poll_job(client, upload.json()["job_id"])

    warn = await client.delete("/api/documents/to-delete.txt")
    assert warn.status_code == 409
    assert "notes-a" in warn.json()["detail"]["collections"]

    confirmed = await client.delete("/api/documents/to-delete.txt", params={"confirm": "true"})
    assert confirmed.status_code == 200

    docs = (await client.get("/api/documents")).json()
    assert all(d["name"] != "to-delete.txt" for d in docs)


async def test_delete_eval_corpus_document_is_refused(tmp_path):
    app = make_app(tmp_path, collections={"rules": ["a.md"]}, eval_doc_names=frozenset(["a.md"]))
    async with _async_client(app) as client:
        response = await client.delete("/api/documents/a.md", params={"confirm": "true"})

    assert response.status_code == 403
