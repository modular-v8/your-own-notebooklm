"""Schema errors, hash mismatch, and tag/answer_location consistency rules."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from raglab.corpus import Document, hash_text
from raglab.evals.goldset import CorpusMismatchError, GoldSetError, load_gold_set, verify_corpus_hashes


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "gold.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_valid_gold_set_loads(tmp_path):
    doc_hash = hash_text("hello world")
    gold = load_gold_set(
        _write(
            tmp_path,
            f"""
            version: 1
            corpus_hashes:
              doc.md: "{doc_hash}"
            entries:
              - id: q-001
                question: "What is X?"
                expected_answer: "X is Y."
                doc: doc.md
                answer_location: {{ type: line_range, start: 1, end: 2 }}
                tags: [factual]
              - id: q-002
                question: "What is Z?"
                expected_answer: null
                doc: doc.md
                answer_location: null
                tags: [not-in-document]
            """,
        )
    )
    assert gold.version == 1
    assert len(gold.entries) == 2


def test_one_malformed_entry_aborts_and_names_it(tmp_path):
    """Acceptance criterion: one deliberately malformed entry aborts before
    any model call, and names that entry."""
    path = _write(
        tmp_path,
        """
        version: 1
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            question: "Fine entry"
            expected_answer: "Y"
            doc: doc.md
            answer_location: { type: line_range, start: 1, end: 2 }
            tags: []
          - id: q-002
            question: "Missing answer_location though not tagged not-in-document"
            expected_answer: "Y"
            doc: doc.md
            answer_location: null
            tags: []
        """,
    )
    with pytest.raises(GoldSetError) as exc_info:
        load_gold_set(path)
    assert any("q-002" in message for message in exc_info.value.messages)


def test_not_in_document_with_answer_location_is_rejected(tmp_path):
    path = _write(
        tmp_path,
        """
        version: 1
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            question: "Q"
            expected_answer: null
            doc: doc.md
            answer_location: { type: line_range, start: 1, end: 2 }
            tags: [not-in-document]
        """,
    )
    with pytest.raises(GoldSetError):
        load_gold_set(path)


def test_duplicate_entry_ids_rejected(tmp_path):
    path = _write(
        tmp_path,
        """
        version: 1
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            question: "First"
            expected_answer: "A"
            doc: doc.md
            answer_location: { type: line_range, start: 1, end: 2 }
            tags: []
          - id: q-001
            question: "Duplicate id"
            expected_answer: "B"
            doc: doc.md
            answer_location: { type: line_range, start: 3, end: 4 }
            tags: []
        """,
    )
    with pytest.raises(GoldSetError) as exc_info:
        load_gold_set(path)
    assert any("duplicate" in message.lower() for message in exc_info.value.messages)


def test_corpus_hash_mismatch_names_file(tmp_path):
    gold = load_gold_set(
        _write(
            tmp_path,
            """
            version: 1
            corpus_hashes:
              doc.md: "sha256:wronghash"
            entries:
              - id: q-001
                question: "Q"
                expected_answer: "A"
                doc: doc.md
                answer_location: { type: line_range, start: 1, end: 2 }
                tags: []
            """,
        )
    )
    documents = {
        "doc.md": Document(
            name="doc.md", path=tmp_path / "doc.md", text="hello world", sha256=hash_text("hello world")
        )
    }
    with pytest.raises(CorpusMismatchError) as exc_info:
        verify_corpus_hashes(gold, documents)
    assert any("doc.md" in message for message in exc_info.value.messages)


def test_corpus_missing_file_named(tmp_path):
    doc_hash = hash_text("hello world")
    gold = load_gold_set(
        _write(
            tmp_path,
            f"""
            version: 1
            corpus_hashes:
              doc.md: "{doc_hash}"
            entries:
              - id: q-001
                question: "Q"
                expected_answer: "A"
                doc: doc.md
                answer_location: {{ type: line_range, start: 1, end: 2 }}
                tags: []
            """,
        )
    )
    with pytest.raises(CorpusMismatchError) as exc_info:
        verify_corpus_hashes(gold, {})
    assert any("doc.md" in message for message in exc_info.value.messages)
