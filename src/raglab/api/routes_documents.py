"""Document upload, listing, membership, and disk deletion.

Upload returns immediately with a job the client polls (spec: embedding a
large PDF is real CPU time; a request held open that long is indistinguishable
from a hang) -- the actual rebuild runs in a background task, serialized
through `state.index_lock` so two uploads never interleave writes to the same
`vectors.npy`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from ..collections import (
    CollectionNotFoundError,
    LockedCollectionError,
)
from ..index.builder import IndexBuilder
from ..parsers.registry import parser_for
from .document_state import derive_document_state
from .indexing import IndexInvarianceError, load_all_documents, rebuild_index, update_document_collections

router = APIRouter()


def _safe_filename(filename: str) -> str:
    # Strip any directory components a client might send -- uploads_dir is
    # the only place this name is ever used to write a file.
    name = Path(filename).name
    if not name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid filename")
    return name


def _existing_document_names(state) -> set[str]:
    return set(load_all_documents(state.corpus_dir, state.uploads_dir))


async def _run_index_job(state, job_id: str, doc: str) -> None:
    state.jobs.set_state(job_id, "parsing")
    async with state.index_lock:
        state.jobs.set_state(job_id, "embedding")
        builder = IndexBuilder(state.store, state.embedder, chunking=state.chunking)
        try:
            results = await asyncio.to_thread(
                rebuild_index,
                state.store,
                builder,
                index_dir=state.index_dir,
                corpus_dir=state.corpus_dir,
                uploads_dir=state.uploads_dir,
                collections=state.collections.all(),
                eval_doc_names=state.eval_doc_names,
            )
        except IndexInvarianceError as exc:
            state.jobs.set_state(job_id, "failed", error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- any build failure must reach the job, not crash the task
            state.jobs.set_state(job_id, "failed", error=str(exc))
            return

        result = next((r for r in results if r.doc == doc), None)
        if result is None:
            state.jobs.set_state(job_id, "failed", error="document not found in build results")
            return
        if result.error:
            state.jobs.set_state(job_id, "failed", error=result.error)
            return

        state.refresh_chunk_cache()
        state.jobs.set_state(job_id, "ready", chunk_count=result.chunk_count)


@router.post("/api/collections/{name}/documents", status_code=202)
async def upload_document(name: str, request: Request, file: UploadFile = File(...)) -> dict:
    state = request.app.state.raglab
    if name in state.collections.locked_names:
        raise HTTPException(status_code=403, detail=f"collection {name!r} is locked and cannot be modified")
    if name not in state.collections.all():
        raise HTTPException(status_code=404, detail=f"collection {name!r} not found")

    doc_name = _safe_filename(file.filename or "")
    try:
        parser_for(Path(doc_name))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unsupported file extension {Path(doc_name).suffix!r}") from None

    if doc_name in _existing_document_names(state):
        raise HTTPException(status_code=409, detail=f"document {doc_name!r} already exists")

    contents = await file.read()
    state.uploads_dir.mkdir(parents=True, exist_ok=True)
    (state.uploads_dir / doc_name).write_bytes(contents)

    state.collections.add_document(name, doc_name)
    job = state.jobs.create(doc_name, name)
    asyncio.create_task(_run_index_job(state, job.job_id, doc_name))

    return {"job_id": job.job_id, "doc": doc_name, "state": job.state}


@router.get("/api/documents")
async def list_documents(request: Request) -> list[dict]:
    state = request.app.state.raglab
    documents = load_all_documents(state.corpus_dir, state.uploads_dir)
    manifest = state.store.load_manifest() if state.store.exists() else None
    manifest_docs = manifest.documents if manifest is not None else {}

    rows = []
    for doc_name in sorted(documents):
        job = state.jobs.latest_for_doc(doc_name)
        entry = manifest_docs.get(doc_name)
        doc_state = derive_document_state(entry is not None, job)
        rows.append(
            {
                "name": doc_name,
                "locked": doc_name in state.eval_doc_names,
                "collections": state.collections.collections_for(doc_name),
                "state": doc_state,
                "chunk_count": entry.chunk_count if entry is not None else None,
                "empty": entry is not None and entry.chunk_count == 0,
                "error": job.error if job is not None and doc_state == "failed" else None,
            }
        )
    return rows


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    state = request.app.state.raglab
    job = state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
    return {
        "job_id": job.job_id,
        "doc": job.doc,
        "collection": job.collection,
        "state": job.state,
        "error": job.error,
        "chunk_count": job.chunk_count,
    }


@router.delete("/api/collections/{name}/documents/{doc}", status_code=204)
async def remove_document_from_collection(name: str, doc: str, request: Request) -> None:
    state = request.app.state.raglab
    try:
        state.collections.remove_document(name, doc)
    except LockedCollectionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if state.store.exists() and doc in state.store.load_manifest().documents:
        async with state.index_lock:
            await asyncio.to_thread(update_document_collections, state.store, doc, state.collections.all())


@router.delete("/api/documents/{doc}")
async def delete_document(doc: str, request: Request, confirm: bool = Query(False)) -> dict:
    state = request.app.state.raglab
    if doc in state.eval_doc_names:
        raise HTTPException(status_code=403, detail=f"{doc!r} is part of the eval corpus and cannot be deleted")

    path = state.uploads_dir / doc
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"document {doc!r} not found")

    referencing = state.collections.collections_for(doc)
    if referencing and not confirm:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"{doc!r} is still referenced by other collections; pass confirm=true to delete anyway",
                "collections": referencing,
            },
        )

    state.collections.remove_document_everywhere(doc)
    path.unlink()

    async with state.index_lock:
        builder = IndexBuilder(state.store, state.embedder, chunking=state.chunking)
        await asyncio.to_thread(
            rebuild_index,
            state.store,
            builder,
            index_dir=state.index_dir,
            corpus_dir=state.corpus_dir,
            uploads_dir=state.uploads_dir,
            collections=state.collections.all(),
            eval_doc_names=state.eval_doc_names,
        )
        state.refresh_chunk_cache()

    return {"deleted": doc}
