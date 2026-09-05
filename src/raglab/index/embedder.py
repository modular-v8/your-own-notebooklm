"""fastembed wrapper: BAAI/bge-small-en-v1.5, CPU, ONNX. No PyTorch.

bge's own model card calls for an instruction prefix on queries only ("query
and passage need different treatment" — the asymmetric-encoding trap this
phase's plan explicitly names). Verified empirically that fastembed's
`TextEmbedding.query_embed()` does NOT apply this for `bge-small-en-v1.5` —
it's a plain alias of `embed()` for this model (fastembed's own model
description calls prefixing "not so necessary" for the v1.5 small variant
and doesn't implement it). Relying on `query_embed()` as originally planned
would silently collapse query and passage encoding to the same vectors, so
the prefix is applied here instead, keeping real asymmetry and making the
`query_embed() != embed()` guard test meaningful.
"""

from __future__ import annotations

import numpy as np
from fastembed import TextEmbedding

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class Embedder:
    model_id = EMBEDDING_MODEL
    dimension = EMBEDDING_DIM

    def __init__(self) -> None:
        self._model = TextEmbedding(model_name=EMBEDDING_MODEL)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return np.array(list(self._model.embed(texts)), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed([QUERY_INSTRUCTION + text])[0]
