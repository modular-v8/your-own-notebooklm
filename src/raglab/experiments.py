"""ExperimentConfig: a named, recorded, reproducible pipeline configuration
(spec: "a named experiment configuration in every run report, sufficient to
reproduce the run"). Every technique this phase tests is a field here;
until its own milestone lands, only `baseline` exists in `experiments.toml`
and reproduces Phases 0-3's fixed defaults exactly.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

DEFAULT_EXPERIMENTS_PATH = Path("experiments.toml")


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: Literal["fixed", "structure"]
    size: int
    overlap: int


def index_subdir_name(chunking: ChunkingConfig) -> str:
    """A chunking config's own directory under the index root (specs/4-
    retrieval-optimization T6.2): different strategies are different
    artifacts and must never share a directory -- `IndexBuilder` refuses to
    write one strategy's chunks into a directory built with another's, but
    this is what keeps two experiments from ever pointing at the same
    directory in the first place."""
    if chunking.strategy == "fixed":
        return f"fixed-{chunking.size}-{chunking.overlap}"
    return chunking.strategy


@dataclass(frozen=True)
class RetrievalConfig:
    mode: Literal["dense", "hybrid"]
    k: int
    candidate_k: int | None = None
    rrf_k: int | None = None


@dataclass(frozen=True)
class RewritingConfig:
    mode: Literal["off", "follow_ups_only", "all_questions"]


@dataclass(frozen=True)
class RerankingConfig:
    mode: Literal["off", "onnx", "llm"]
    model: str | None = None


@dataclass(frozen=True)
class AgenticConfig:
    max_calls: int
    # Retain only the top-N accumulated chunks by score, across every search
    # call, instead of their union (specs/5-adaptive-retrieval). None keeps
    # today's unpruned behavior.
    prune_top_n: int | None = None
    # specs/5-adaptive-retrieval T6.1: adds one citation-discipline sentence
    # to the system prompt. False keeps agentic-v1 byte-identical to Phase
    # 4's frozen baseline -- T6.2 measured this opt-in and found no net
    # benefit, so it is never the default.
    tight_citations: bool = False


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    rewriting: RewritingConfig | None = None
    reranking: RerankingConfig | None = None
    agentic: AgenticConfig | None = None


class ExperimentsError(Exception):
    pass


def _chunking_from_raw(raw: dict[str, Any]) -> ChunkingConfig:
    return ChunkingConfig(strategy=raw["strategy"], size=int(raw["size"]), overlap=int(raw["overlap"]))


def _retrieval_from_raw(raw: dict[str, Any]) -> RetrievalConfig:
    return RetrievalConfig(
        mode=raw["mode"],
        k=int(raw["k"]),
        candidate_k=int(raw["candidate_k"]) if "candidate_k" in raw else None,
        rrf_k=int(raw["rrf_k"]) if "rrf_k" in raw else None,
    )


def _rewriting_from_raw(raw: dict[str, Any] | None) -> RewritingConfig | None:
    return None if raw is None else RewritingConfig(mode=raw["mode"])


def _reranking_from_raw(raw: dict[str, Any] | None) -> RerankingConfig | None:
    return None if raw is None else RerankingConfig(mode=raw["mode"], model=raw.get("model"))


def _agentic_from_raw(raw: dict[str, Any] | None) -> AgenticConfig | None:
    if raw is None:
        return None
    prune_top_n = int(raw["prune_top_n"]) if "prune_top_n" in raw else None
    tight_citations = bool(raw["tight_citations"]) if "tight_citations" in raw else False
    return AgenticConfig(max_calls=int(raw["max_calls"]), prune_top_n=prune_top_n, tight_citations=tight_citations)


def load_experiments(path: Path = DEFAULT_EXPERIMENTS_PATH) -> dict[str, ExperimentConfig]:
    if not path.exists():
        raise ExperimentsError(f"{path}: file not found")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    experiments: dict[str, ExperimentConfig] = {}
    for name, entry in raw.items():
        try:
            experiments[name] = ExperimentConfig(
                name=name,
                chunking=_chunking_from_raw(entry["chunking"]),
                retrieval=_retrieval_from_raw(entry["retrieval"]),
                rewriting=_rewriting_from_raw(entry.get("rewriting")),
                reranking=_reranking_from_raw(entry.get("reranking")),
                agentic=_agentic_from_raw(entry.get("agentic")),
            )
        except KeyError as exc:
            raise ExperimentsError(f"{path}: experiment {name!r} missing required field {exc}") from exc
    return experiments
