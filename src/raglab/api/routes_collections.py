"""GET /api/collections -- reads config.toml, never manages membership
(spec: "The UI reads collections rather than managing them")."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/collections")
async def list_collections(request: Request) -> list[dict]:
    state = request.app.state.raglab
    return [{"name": name, "documents": docs} for name, docs in state.config.collections.items()]
