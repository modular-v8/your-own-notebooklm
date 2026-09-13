"""Derived document state (plan.md): a document is on disk or not, in the
manifest or not, and has an active job or not. Those three facts give every
state the sidebar needs -- nothing is stored or reconciled after a crash."""

from __future__ import annotations

from typing import Literal

from .jobs import IndexJob

DocumentState = Literal["ready", "reindexing", "indexing", "failed"]

_ACTIVE_JOB_STATES = ("queued", "parsing", "embedding")


def derive_document_state(in_manifest: bool, job: IndexJob | None) -> DocumentState:
    active = job is not None and job.state in _ACTIVE_JOB_STATES
    if in_manifest:
        return "reindexing" if active else "ready"
    return "indexing" if active else "failed"
