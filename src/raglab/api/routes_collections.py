"""Collection CRUD. `config.toml`'s collections never reach here -- every
route reads and writes through `CollectionRegistry.user()` only, so a
request naming one is refused exactly like a nonexistent collection (spec
amendment: "a person using the web app never learns they exist"). `create`
is the one exception, needing a distinct rejection for a reserved name --
enforced here, at the API, never merely hidden by the UI (spec: "a UI that
merely omits something is not protection")."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..collections import CollectionNameConflictError, CollectionNotFoundError

router = APIRouter()


class CreateCollectionRequest(BaseModel):
    name: str


class RenameCollectionRequest(BaseModel):
    name: str


@router.get("/api/collections")
async def list_collections(request: Request) -> list[dict]:
    state = request.app.state.raglab
    return state.collections.list_summary()


@router.post("/api/collections", status_code=201)
async def create_collection(body: CreateCollectionRequest, request: Request) -> dict:
    state = request.app.state.raglab
    try:
        state.collections.create(body.name)
    except CollectionNameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"name": body.name, "document_count": 0}


@router.patch("/api/collections/{name}")
async def rename_collection(name: str, body: RenameCollectionRequest, request: Request) -> dict:
    state = request.app.state.raglab
    try:
        state.collections.rename(name, body.name)
    except CollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CollectionNameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"name": body.name}


@router.delete("/api/collections/{name}", status_code=204)
async def delete_collection(name: str, request: Request) -> None:
    state = request.app.state.raglab
    try:
        state.collections.delete(name)
    except CollectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
