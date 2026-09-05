"""config.toml + environment override, typed.

Secrets (ANTHROPIC_API_KEY, OPENROUTER_API_KEY) live only in the environment;
everything else clone-and-run needs is one readable file. `RAGLAB_PROVIDER`
overrides `[provider].name` without touching the file, satisfying "no code
change required to switch providers" for a quick one-off run.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .providers.registry import ProviderName, auto_select

DEFAULT_CONFIG_PATH = Path("config.toml")
DEFAULT_CONCURRENCY = 5
DEFAULT_ANSWER_MODEL = "claude-sonnet-5"
DEFAULT_JUDGE_MODEL = "claude-opus-5"
DEFAULT_TOP_K = 5
DEFAULT_SCORE_THRESHOLD = 0.35


@dataclass(frozen=True)
class RoleConfig:
    provider: ProviderName
    model: str


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int
    score_threshold: float


@dataclass(frozen=True)
class RagLabConfig:
    answer: RoleConfig
    judge: RoleConfig
    concurrency: int
    retrieval: RetrievalConfig

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> RagLabConfig:
        raw = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

        provider_name = os.environ.get("RAGLAB_PROVIDER") or raw.get("provider", {}).get(
            "name", "auto"
        )
        if provider_name == "auto":
            provider_name = auto_select()

        answer_raw = raw.get("answer", {})
        answer = RoleConfig(
            provider=answer_raw.get("provider", provider_name),
            model=answer_raw.get("model", DEFAULT_ANSWER_MODEL),
        )

        # Judge model is pinned independently of the answer model so swapping
        # the answer model never moves the ruler; judge provider defaults to
        # the same resolved provider so clone-and-run works with one credential.
        judge_raw = raw.get("judge", {})
        judge = RoleConfig(
            provider=judge_raw.get("provider", provider_name),
            model=judge_raw.get("model", DEFAULT_JUDGE_MODEL),
        )

        concurrency = int(raw.get("run", {}).get("concurrency", DEFAULT_CONCURRENCY))

        retrieval_raw = raw.get("retrieval", {})
        retrieval = RetrievalConfig(
            top_k=int(retrieval_raw.get("top_k", DEFAULT_TOP_K)),
            score_threshold=float(retrieval_raw.get("score_threshold", DEFAULT_SCORE_THRESHOLD)),
        )

        return cls(answer=answer, judge=judge, concurrency=concurrency, retrieval=retrieval)
