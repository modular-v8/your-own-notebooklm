"""ONNX cross-encoder reranker (specs/4-retrieval-optimization T2.6/T4.1).

T2.6 probed `fastembed.rerank.cross_encoder.TextCrossEncoder`: pure ONNX
(`onnxruntime`), no PyTorch import anywhere in the module -- satisfies the
no-PyTorch constraint outright, so the LLM-reranker fallback plan.md
carried as a risk mitigation isn't needed. `Xenova/ms-marco-MiniLM-L-6-v2`
is the smallest model (0.08 GB): 40s cold load (one-time download), 0.24s
warm, negligible per-query cost.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastembed.rerank.cross_encoder import TextCrossEncoder

DEFAULT_RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


@dataclass(frozen=True)
class RerankedChunk:
    chunk_id: str
    score: float


class Reranker:
    """Loads the ONNX model once and reuses it across every `rerank` call --
    the model load (not the per-query score pass) is the expensive part."""

    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL):
        self._model_name = model_name
        self._encoder: TextCrossEncoder | None = None

    def _model(self) -> TextCrossEncoder:
        if self._encoder is None:
            self._encoder = TextCrossEncoder(model_name=self._model_name)
        return self._encoder

    def rerank(self, query: str, candidates: list[tuple[str, str]]) -> list[RerankedChunk]:
        """`candidates` is (chunk_id, text) pairs in their incoming
        (candidate_k) order. Returns every candidate, re-scored and sorted
        best-first -- truncation to `k` is the caller's job (`retriever.py`),
        the same split of responsibility dense and BM25 search already use.
        """
        if not candidates:
            return []
        texts = [text for _, text in candidates]
        scores = list(self._model().rerank(query, texts))
        reranked = [
            RerankedChunk(chunk_id, float(score)) for (chunk_id, _), score in zip(candidates, scores)
        ]
        reranked.sort(key=lambda r: -r.score)
        return reranked
