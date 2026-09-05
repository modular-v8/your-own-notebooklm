"""Asymmetry guard: query_embed must differ from embed for the same string.

Marked integration because it needs the real fastembed/bge-small-en-v1.5
ONNX model, which fastembed downloads over the network on first use --
AGENT.md requires the default test run to work with no network access, so
this is excluded from it the same way live-provider tests are.
"""

from __future__ import annotations

import numpy as np
import pytest

from raglab.index.embedder import Embedder

pytestmark = pytest.mark.integration


def test_query_embedding_differs_from_passage_embedding():
    embedder = Embedder()
    text = "What is the minimum age for a team member?"

    passage_vector = embedder.embed([text])[0]
    query_vector = embedder.embed_query(text)

    assert not np.allclose(passage_vector, query_vector)


def test_embedding_has_configured_dimension():
    embedder = Embedder()
    vectors = embedder.embed(["hello world"])
    assert vectors.shape == (1, embedder.dimension)
