"""Structure-aware chunking (specs/4-retrieval-optimization T6.1)."""

from __future__ import annotations

from raglab.index.chunker import MAX_STRUCTURE_CHUNK_CHARS, chunk_text_structure


def test_rule_id_boundaries_are_respected():
    text = (
        "T3.17.2 The Impact Attenuator must be at least 100 mm high.\n"
        "It must not penetrate the bulkhead.\n"
        "T3.17.3 The AIP must match the bulkhead's outside dimensions.\n"
    )
    chunks = chunk_text_structure("doc.pdf", text)

    assert [c.text.splitlines()[0] for c in chunks] == [
        "T3.17.2 The Impact Attenuator must be at least 100 mm high.",
        "T3.17.3 The AIP must match the bulkhead's outside dimensions.",
    ]


def test_markdown_heading_boundaries_are_respected():
    text = "# Intro\nSome intro text.\n## Section One\nDetails about section one.\n"
    chunks = chunk_text_structure("doc.md", text)

    assert [c.text.splitlines()[0] for c in chunks] == ["# Intro", "## Section One"]


def test_preamble_before_first_boundary_becomes_its_own_leading_chunk():
    text = "Some preamble with no heading.\nT1.1 First real rule.\n"
    chunks = chunk_text_structure("doc.pdf", text)

    assert chunks[0].char_start == 0
    assert chunks[0].text == "Some preamble with no heading.\n"
    assert chunks[1].text.startswith("T1.1")


def test_mid_sentence_rule_id_reference_is_not_a_boundary():
    """A cross-reference like "...as required by T3.2.4." mid-line must not
    fragment the chunk -- only a line-initial rule id starts a new one."""
    text = "T1.1 The first rule references T3.2.4 in passing, but stays whole.\nT1.2 The second rule.\n"
    chunks = chunk_text_structure("doc.pdf", text)

    assert len(chunks) == 2
    assert "T3.2.4" in chunks[0].text
    assert chunks[0].text.startswith("T1.1")


def test_no_chunk_exceeds_the_max_char_ceiling():
    # One giant segment under a single heading, well over the sub-split threshold.
    body = "word " * 1000  # 5000 chars, no internal rule ids or headings
    text = f"# Big Section\n{body}"
    chunks = chunk_text_structure("doc.md", text, max_chars=500, overlap=50)

    assert len(chunks) > 1
    assert all(len(c.text) <= 500 for c in chunks)


def test_no_source_text_lost_between_chunks():
    text = (
        "Preamble.\n"
        "T1.1 " + ("alpha " * 200) + "\n"
        "T1.2 " + ("bravo " * 5) + "\n"
        "# Heading\ncharlie delta echo.\n"
    )
    chunks = chunk_text_structure("doc.pdf", text, max_chars=300, overlap=50)

    assert chunks[0].char_start == 0
    assert chunks[-1].char_end == len(text)
    for prev, nxt in zip(chunks, chunks[1:]):
        # No gap: the next chunk starts at or before the previous one ends
        # (overlap is allowed within a sub-split segment; a gap is not).
        assert nxt.char_start <= prev.char_end


def test_empty_text_returns_no_chunks():
    assert chunk_text_structure("doc.md", "") == []


def test_default_max_chars_matches_the_512_token_ceiling():
    assert MAX_STRUCTURE_CHUNK_CHARS == 2000
