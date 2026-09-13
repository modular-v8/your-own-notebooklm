"""Derived document state: on disk / in manifest / active job -> the four
states the sidebar shows (plan.md's table)."""

from __future__ import annotations

from raglab.api.document_state import derive_document_state
from raglab.api.jobs import IndexJob


def _job(state: str) -> IndexJob:
    return IndexJob(job_id="j1", doc="a.md", collection="notes", state=state)


def test_ready_when_in_manifest_and_no_active_job():
    assert derive_document_state(True, None) == "ready"
    assert derive_document_state(True, _job("ready")) == "ready"
    assert derive_document_state(True, _job("failed")) == "ready"


def test_indexing_when_not_in_manifest_and_job_active():
    for state in ("queued", "parsing", "embedding"):
        assert derive_document_state(False, _job(state)) == "indexing"


def test_reindexing_when_in_manifest_and_job_active():
    for state in ("queued", "parsing", "embedding"):
        assert derive_document_state(True, _job(state)) == "reindexing"


def test_failed_when_not_in_manifest_and_no_active_job():
    assert derive_document_state(False, None) == "failed"
    assert derive_document_state(False, _job("failed")) == "failed"
