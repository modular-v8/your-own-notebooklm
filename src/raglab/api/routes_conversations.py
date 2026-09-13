"""Conversation lifecycle: create, read, ask a question (SSE), escalate a
turn. No answering logic lives here -- every handler is a thin wrapper over
`RetrievalPipeline`/`AgenticPipeline` and `ConversationStore`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..pipelines.base import ConversationTurn, Query
from ..providers.base import OverContextError, ProviderAuthError
from .store import AnswerRecord, ConversationNotFoundError, ConversationRecord, Turn

router = APIRouter()

BASELINE_PIPELINE_NAME = "baseline"
AGENTIC_PIPELINE_NAME = "agentic"


class CreateConversationRequest(BaseModel):
    collection: str


class TurnRequest(BaseModel):
    question: str


def _history(conversation: ConversationRecord, upto: int | None = None) -> list[ConversationTurn]:
    """Prior turns as (question, baseline answer) pairs -- the baseline
    pipeline's own text is what a follow-up's history is built from,
    matching Phase 3's semantics regardless of whether a turn was later
    escalated (spec: history sent to the model, escalation is a separate,
    user-triggered comparison, never a silent substitute)."""
    turns = conversation.turns if upto is None else conversation.turns[:upto]
    return [ConversationTurn(question=t.question, answer=t.baseline.text) for t in turns]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _load_conversation(request: Request, conversation_id: str) -> ConversationRecord:
    state = request.app.state.raglab
    try:
        return state.conversation_store.load(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail=f"conversation {conversation_id!r} not found") from None


@router.post("/api/conversations")
async def create_conversation(body: CreateConversationRequest, request: Request) -> ConversationRecord:
    state = request.app.state.raglab
    known = state.collections.user()
    if body.collection not in known:
        raise HTTPException(
            status_code=400,
            detail=f"unknown collection {body.collection!r}; known: {sorted(known)}",
        )
    return state.conversation_store.create(body.collection)


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> ConversationRecord:
    return _load_conversation(request, conversation_id)


async def _stream_turn(request: Request, conversation: ConversationRecord, question: str) -> AsyncIterator[str]:
    state = request.app.state.raglab
    query = Query(question=question, doc_hint="", history=_history(conversation), collection=conversation.collection)

    emitted: list[str] = []
    result = None
    error_message: str | None = None

    try:
        async for piece in state.baseline_pipeline.answer_stream(query):
            if piece.done:
                result = piece.result
                break
            if piece.text:
                emitted.append(piece.text)
                yield _sse("token", {"text": piece.text})
    except (OverContextError, ProviderAuthError) as exc:
        error_message = str(exc)
    except Exception as exc:  # noqa: BLE001 -- any provider/transport failure must reach the conversation, not crash the stream
        error_message = str(exc)

    if result is not None:
        answer = AnswerRecord(text=result.answer, cited=result.cited, pipeline=BASELINE_PIPELINE_NAME)
    else:
        # Provider failed mid-stream: keep whatever prose already arrived
        # rather than discarding the turn (spec: unwanted behavior).
        answer = AnswerRecord(
            text="".join(emitted), cited=None, pipeline=BASELINE_PIPELINE_NAME, error=error_message
        )

    conversation.turns.append(Turn(question=question, baseline=answer))
    state.conversation_store.save(conversation)

    if error_message is not None:
        yield _sse("error", {"message": error_message})
    else:
        yield _sse("citations", {"cited": answer.cited})
    yield _sse("done", {})


@router.post("/api/conversations/{conversation_id}/turns")
async def create_turn(conversation_id: str, body: TurnRequest, request: Request) -> StreamingResponse:
    conversation = _load_conversation(request, conversation_id)
    return StreamingResponse(_stream_turn(request, conversation, body.question), media_type="text/event-stream")


@router.post("/api/conversations/{conversation_id}/turns/{turn_index}/escalate")
async def escalate_turn(conversation_id: str, turn_index: int, request: Request) -> AnswerRecord:
    state = request.app.state.raglab
    conversation = _load_conversation(request, conversation_id)

    if turn_index < 0 or turn_index >= len(conversation.turns):
        raise HTTPException(status_code=404, detail=f"turn {turn_index} not found")

    turn = conversation.turns[turn_index]
    if turn.agentic is not None:
        return turn.agentic  # cached: a second escalation must not pay for it again (spec)

    query = Query(
        question=turn.question,
        doc_hint="",
        history=_history(conversation, upto=turn_index),
        collection=conversation.collection,
    )

    try:
        result = await state.agentic_pipeline.answer(query)
    except (OverContextError, ProviderAuthError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    answer = AnswerRecord(text=result.answer, cited=result.cited, pipeline=AGENTIC_PIPELINE_NAME)
    conversation.turns[turn_index].agentic = answer
    state.conversation_store.save(conversation)
    return answer
