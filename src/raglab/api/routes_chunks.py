"""GET /api/chunks/{chunk_id} -- resolves a cited chunk id to its text,
document, and line range for the source panel. Read-only: the line range is
computed from the chunk's stored char span at request time, nothing in the
index changes (plan.md)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..evals.locations import line_of_offset

router = APIRouter()


@router.get("/api/chunks/{chunk_id}")
async def get_chunk(chunk_id: str, request: Request) -> dict:
    state = request.app.state.raglab
    chunk = state.chunks_by_id.get(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail=f"chunk {chunk_id!r} not found in index")

    doc_text = state.doc_texts.get(chunk.doc)
    if doc_text is None:
        raise HTTPException(status_code=404, detail=f"document {chunk.doc!r} text unavailable")

    line_start = line_of_offset(doc_text, chunk.char_start)
    line_end = line_of_offset(doc_text, max(chunk.char_start, chunk.char_end - 1))
    return {
        "chunk_id": chunk.chunk_id,
        "doc": chunk.doc,
        "text": chunk.text,
        "line_start": line_start,
        "line_end": line_end,
    }
