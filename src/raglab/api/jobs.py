"""In-memory index-job table: one record per upload, polled by the sidebar
while a document moves through parsing/embedding.

Not persisted (plan.md: "a job that didn't finish should be retried rather
than resumed"). A server restart mid-index leaves the uploaded file on disk
without a manifest entry, which `derive_document_state` (routes_documents.py)
already reads as `failed` -- there is nothing here to reconcile.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

JobState = Literal["queued", "parsing", "embedding", "ready", "failed"]


@dataclass
class IndexJob:
    job_id: str
    doc: str
    collection: str
    state: JobState = "queued"
    error: str | None = None
    chunk_count: int | None = None


class JobTable:
    def __init__(self) -> None:
        self._jobs: dict[str, IndexJob] = {}
        self._latest_by_doc: dict[str, str] = {}

    def create(self, doc: str, collection: str) -> IndexJob:
        job = IndexJob(job_id=uuid.uuid4().hex, doc=doc, collection=collection)
        self._jobs[job.job_id] = job
        self._latest_by_doc[doc] = job.job_id
        return job

    def get(self, job_id: str) -> IndexJob | None:
        return self._jobs.get(job_id)

    def latest_for_doc(self, doc: str) -> IndexJob | None:
        job_id = self._latest_by_doc.get(doc)
        return self._jobs.get(job_id) if job_id else None

    def set_state(self, job_id: str, state: JobState, *, error: str | None = None, chunk_count: int | None = None) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.state = state
        if error is not None:
            job.error = error
        if chunk_count is not None:
            job.chunk_count = chunk_count
