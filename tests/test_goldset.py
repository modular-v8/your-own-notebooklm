"""Schema errors, hash mismatch, and tag/sources consistency rules."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from raglab.corpus import Document, hash_bytes
from raglab.evals.goldset import (
    NOT_IN_DOCUMENT_TAG,
    CorpusMismatchError,
    GoldSetError,
    check_tag_vocabulary,
    load_gold_set,
    verify_corpus_hashes,
)


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "gold.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_valid_gold_set_loads(tmp_path):
    doc_hash = hash_bytes(b"hello world")
    gold = load_gold_set(
        _write(
            tmp_path,
            f"""
            version: 3
            collection: everything
            corpus_hashes:
              doc.md: "{doc_hash}"
            entries:
              - id: q-001
                turns:
                  - question: "What is X?"
                expected_answer: "X is Y."
                sources:
                  - doc: doc.md
                    answer_location: {{ type: line_range, start: 1, end: 2 }}
                tags: [lexical-anchor]
              - id: q-002
                turns:
                  - question: "What is Z?"
                expected_answer: null
                sources: []
                tags: [not-in-document]
            """,
        )
    )
    assert gold.version == 3
    assert gold.collection == "everything"
    assert len(gold.entries) == 2
    assert gold.entries[0].docs == ["doc.md"]
    assert gold.entries[0].question == "What is X?"
    assert gold.entries[1].docs == []


def test_version_1_is_rejected_naming_the_migration(tmp_path):
    path = _write(
        tmp_path,
        """
        version: 1
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            question: "Q"
            expected_answer: "A"
            doc: doc.md
            answer_location: { type: line_range, start: 1, end: 2 }
            tags: []
        """,
    )
    with pytest.raises(GoldSetError) as exc_info:
        load_gold_set(path)
    assert any("migrat" in message.lower() for message in exc_info.value.messages)


def test_version_2_is_rejected_naming_the_migration(tmp_path):
    path = _write(
        tmp_path,
        """
        version: 2
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            question: "Q"
            expected_answer: "A"
            sources:
              - doc: doc.md
                answer_location: { type: line_range, start: 1, end: 2 }
            tags: []
        """,
    )
    with pytest.raises(GoldSetError) as exc_info:
        load_gold_set(path)
    assert any("migrat" in message.lower() for message in exc_info.value.messages)
    assert any("turns" in message for message in exc_info.value.messages)


def test_one_malformed_entry_aborts_and_names_it(tmp_path):
    """Acceptance criterion: one deliberately malformed entry aborts before
    any model call, and names that entry."""
    path = _write(
        tmp_path,
        """
        version: 3
        collection: everything
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            turns:
              - question: "Fine entry"
            expected_answer: "Y"
            sources:
              - doc: doc.md
                answer_location: { type: line_range, start: 1, end: 2 }
            tags: []
          - id: q-002
            turns:
              - question: "Missing sources though not tagged not-in-document"
            expected_answer: "Y"
            sources: []
            tags: []
        """,
    )
    with pytest.raises(GoldSetError) as exc_info:
        load_gold_set(path)
    assert any("q-002" in message for message in exc_info.value.messages)


def test_not_in_document_with_sources_is_rejected(tmp_path):
    path = _write(
        tmp_path,
        """
        version: 3
        collection: everything
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            turns:
              - question: "Q"
            expected_answer: null
            sources:
              - doc: doc.md
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
        version: 3
        collection: everything
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            turns:
              - question: "First"
            expected_answer: "A"
            sources:
              - doc: doc.md
                answer_location: { type: line_range, start: 1, end: 2 }
            tags: []
          - id: q-001
            turns:
              - question: "Duplicate id"
            expected_answer: "B"
            sources:
              - doc: doc.md
                answer_location: { type: line_range, start: 3, end: 4 }
            tags: []
        """,
    )
    with pytest.raises(GoldSetError) as exc_info:
        load_gold_set(path)
    assert any("duplicate" in message.lower() for message in exc_info.value.messages)


def test_multi_source_entry_spans_two_documents(tmp_path):
    gold = load_gold_set(
        _write(
            tmp_path,
            """
            version: 3
            collection: everything
            corpus_hashes:
              a.md: "sha256:aaaa"
              b.md: "sha256:bbbb"
            entries:
              - id: q-001
                turns:
                  - question: "Cross-doc question"
                expected_answer: "Answer spanning both."
                sources:
                  - doc: a.md
                    answer_location: { type: line_range, start: 1, end: 1 }
                  - doc: b.md
                    answer_location: { type: line_range, start: 2, end: 2 }
                tags: [cross-document, synthesis]
            """,
        )
    )
    assert gold.entries[0].docs == ["a.md", "b.md"]
    assert gold.primary_doc in ("a.md", "b.md")


def test_occurrence_only_allowed_on_section(tmp_path):
    path = _write(
        tmp_path,
        """
        version: 3
        collection: everything
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            turns:
              - question: "Q"
            expected_answer: "A"
            sources:
              - doc: doc.md
                answer_location: { type: line_range, start: 1, end: 2, occurrence: last }
            tags: []
        """,
    )
    with pytest.raises(GoldSetError):
        load_gold_set(path)


def test_docs_referenced_must_be_in_corpus_hashes(tmp_path):
    path = _write(
        tmp_path,
        """
        version: 3
        collection: everything
        corpus_hashes:
          doc.md: "sha256:deadbeef"
        entries:
          - id: q-001
            turns:
              - question: "Q"
            expected_answer: "A"
            sources:
              - doc: other.md
                answer_location: { type: line_range, start: 1, end: 2 }
            tags: []
        """,
    )
    with pytest.raises(GoldSetError) as exc_info:
        load_gold_set(path)
    assert any("other.md" in message for message in exc_info.value.messages)


def test_check_tag_vocabulary_warns_on_untagged_entry(tmp_path):
    gold = load_gold_set(
        _write(
            tmp_path,
            """
            version: 3
            collection: everything
            corpus_hashes:
              doc.md: "sha256:deadbeef"
            entries:
              - id: q-001
                turns:
                  - question: "Q"
                expected_answer: "A"
                sources:
                  - doc: doc.md
                    answer_location: { type: line_range, start: 1, end: 2 }
                tags: [made-up-free-tag]
            """,
        )
    )
    warnings = check_tag_vocabulary(gold)
    assert any("q-001" in w for w in warnings)


def test_check_tag_vocabulary_silent_when_vocab_tag_present(tmp_path):
    gold = load_gold_set(
        _write(
            tmp_path,
            f"""
            version: 3
            collection: everything
            corpus_hashes:
              doc.md: "sha256:deadbeef"
            entries:
              - id: q-001
                turns:
                  - question: "Q"
                expected_answer: null
                sources: []
                tags: [{NOT_IN_DOCUMENT_TAG}]
            """,
        )
    )
    assert check_tag_vocabulary(gold) == []


def test_corpus_hash_mismatch_names_file(tmp_path):
    gold = load_gold_set(
        _write(
            tmp_path,
            """
            version: 3
            collection: everything
            corpus_hashes:
              doc.md: "sha256:wronghash"
            entries:
              - id: q-001
                turns:
                  - question: "Q"
                expected_answer: "A"
                sources:
                  - doc: doc.md
                    answer_location: { type: line_range, start: 1, end: 2 }
                tags: []
            """,
        )
    )
    documents = {
        "doc.md": Document(name="doc.md", path=tmp_path / "doc.md", sha256=hash_bytes(b"hello world"))
    }
    with pytest.raises(CorpusMismatchError) as exc_info:
        verify_corpus_hashes(gold, documents)
    assert any("doc.md" in message for message in exc_info.value.messages)


def test_corpus_missing_file_named(tmp_path):
    doc_hash = hash_bytes(b"hello world")
    gold = load_gold_set(
        _write(
            tmp_path,
            f"""
            version: 3
            collection: everything
            corpus_hashes:
              doc.md: "{doc_hash}"
            entries:
              - id: q-001
                turns:
                  - question: "Q"
                expected_answer: "A"
                sources:
                  - doc: doc.md
                    answer_location: {{ type: line_range, start: 1, end: 2 }}
                tags: []
            """,
        )
    )
    with pytest.raises(CorpusMismatchError) as exc_info:
        verify_corpus_hashes(gold, {})
    assert any("doc.md" in message for message in exc_info.value.messages)
