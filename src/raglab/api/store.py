"""ConversationStore: one JSON file per conversation, files over a database
(spec: data & integrations) -- inspectable by hand, survives a server
restart, no schema migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

CONVERSATION_ID_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%SZ"
DEFAULT_CONVERSATIONS_DIR = Path("conversations")


class AnswerRecord(BaseModel):
    text: str
    # None: no <citations> block was found (uncited). Empty list: a block
    # was found naming nothing. Same distinction as PipelineResult.cited.
    cited: list[str] | None = None
    pipeline: str
    # Set only when the provider errored mid-stream/mid-call -- `text`
    # still holds whatever partial answer was produced (spec: unwanted
    # behavior, preserve the partial answer rather than discarding the turn).
    error: str | None = None


class Turn(BaseModel):
    question: str
    baseline: AnswerRecord
    agentic: AnswerRecord | None = None


class ConversationRecord(BaseModel):
    id: str
    collection: str
    created_at: str
    turns: list[Turn] = []


def new_conversation_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime(CONVERSATION_ID_TIMESTAMP_FORMAT)
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


class ConversationNotFoundError(Exception):
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        super().__init__(f"conversation {conversation_id!r} not found")


class ConversationStore:
    def __init__(self, directory: Path = DEFAULT_CONVERSATIONS_DIR):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, conversation_id: str) -> Path:
        return self.directory / f"{conversation_id}.json"

    def create(self, collection: str) -> ConversationRecord:
        record = ConversationRecord(
            id=new_conversation_id(),
            collection=collection,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save(record)
        return record

    def load(self, conversation_id: str) -> ConversationRecord:
        path = self._path(conversation_id)
        if not path.exists():
            raise ConversationNotFoundError(conversation_id)
        return ConversationRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, record: ConversationRecord) -> None:
        self._path(record.id).write_text(record.model_dump_json(indent=2), encoding="utf-8")
