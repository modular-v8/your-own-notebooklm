"""Chunk spans are contiguous with the configured overlap, and no text is lost."""

from __future__ import annotations

from raglab.index.chunker import chunk_text


def test_empty_text_produces_no_chunks():
    assert chunk_text("doc.md", "") == []


def test_short_text_is_one_chunk():
    text = "hello world"
    chunks = chunk_text("doc.md", text, size=900, overlap=150)
    assert len(chunks) == 1
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)
    assert chunks[0].text == text
    assert chunks[0].chunk_id == "doc.md:0000"


def test_chunks_overlap_by_configured_amount():
    text = "a" * 2500
    chunks = chunk_text("doc.md", text, size=900, overlap=150)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.char_start == prev.char_end - 150
        assert nxt.ordinal == prev.ordinal + 1


def test_no_text_lost_across_chunks():
    text = "".join(str(i % 10) for i in range(2500))
    chunks = chunk_text("doc.md", text, size=900, overlap=150)
    # Every character of the source is covered by the union of chunk spans.
    covered = set()
    for chunk in chunks:
        covered.update(range(chunk.char_start, chunk.char_end))
        assert chunk.text == text[chunk.char_start : chunk.char_end]
    assert covered == set(range(len(text)))


def test_last_chunk_ends_exactly_at_text_end():
    text = "a" * 2500
    chunks = chunk_text("doc.md", text, size=900, overlap=150)
    assert chunks[-1].char_end == len(text)


def test_chunk_ids_are_stable_and_sortable():
    text = "a" * 3000
    chunks = chunk_text("mydoc.md", text, size=900, overlap=150)
    ids = [c.chunk_id for c in chunks]
    assert ids == sorted(ids)
    assert all(cid.startswith("mydoc.md:") for cid in ids)
