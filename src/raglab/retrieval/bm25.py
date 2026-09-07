"""Hand-rolled BM25 over chunk text (plan.md Tech Stack: "It is a term-frequency
and IDF formula, not a library-shaped problem"). `k1=1.2`, `b=0.75` are the
standard defaults, not swept -- sweeping them is out of scope the same way
chunk size is.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ..index.store import StoredChunk

K1 = 1.2
B = 0.75

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class BM25Hit:
    chunk_id: str
    score: float


class BM25Index:
    """Built once over a fixed set of chunks; `search` never mutates state."""

    def __init__(self, chunks: list[StoredChunk], *, k1: float = K1, b: float = B):
        self.k1 = k1
        self.b = b
        self.chunks = list(chunks)

        doc_tokens = [tokenize(chunk.text) for chunk in self.chunks]
        self._doc_lengths = [len(toks) for toks in doc_tokens]
        self._avg_doc_length = (sum(self._doc_lengths) / len(self._doc_lengths)) if self._doc_lengths else 0.0

        self._term_frequencies: list[dict[str, int]] = []
        document_frequency: dict[str, int] = {}
        for toks in doc_tokens:
            tf: dict[str, int] = {}
            for tok in toks:
                tf[tok] = tf.get(tok, 0) + 1
            self._term_frequencies.append(tf)
            for term in tf:
                document_frequency[term] = document_frequency.get(term, 0) + 1

        n = len(self.chunks)
        # Standard BM25 idf: log((N - df + 0.5) / (df + 0.5) + 1) -- the "+ 1"
        # inside the log keeps idf positive even when a term appears in every
        # document, unlike the classic Robertson-Sparck Jones formula.
        self._idf = {term: math.log((n - df + 0.5) / (df + 0.5) + 1) for term, df in document_frequency.items()}

    def _score(self, doc_index: int, query_terms: list[str]) -> float:
        tf = self._term_frequencies[doc_index]
        doc_length = self._doc_lengths[doc_index]
        score = 0.0
        for term in query_terms:
            term_freq = tf.get(term, 0)
            if term_freq == 0:
                continue
            idf = self._idf.get(term, 0.0)
            numerator = term_freq * (self.k1 + 1)
            denominator = term_freq + self.k1 * (1 - self.b + self.b * doc_length / self._avg_doc_length)
            score += idf * (numerator / denominator)
        return score

    def search(self, query: str, k: int, collection: str | None = None) -> list[BM25Hit]:
        query_terms = tokenize(query)
        scored: list[tuple[int, float]] = []
        for i, chunk in enumerate(self.chunks):
            if collection is not None and collection not in chunk.collections:
                continue
            score = self._score(i, query_terms)
            if score > 0:
                scored.append((i, score))
        scored.sort(key=lambda pair: -pair[1])
        return [BM25Hit(self.chunks[i].chunk_id, score) for i, score in scored[:k]]
