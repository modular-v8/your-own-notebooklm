"""Model aliases: one name the caller uses, mapped to each provider's id.

Frozen registry rather than free-text model strings in config, so a typo in
config.toml fails at startup instead of as a confusing 404 mid-run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    context_window: int
    anthropic_id: str
    openrouter_id: str


MODEL_REGISTRY: dict[str, ModelSpec] = {
    "claude-sonnet-5": ModelSpec(
        alias="claude-sonnet-5",
        context_window=200_000,
        anthropic_id="claude-sonnet-5",
        openrouter_id="anthropic/claude-sonnet-5",
    ),
    "claude-opus-5": ModelSpec(
        alias="claude-opus-5",
        context_window=200_000,
        anthropic_id="claude-opus-5",
        openrouter_id="anthropic/claude-opus-5",
    ),
    # 4.5-generation model (Phase 7): does not take the 5-family's
    # thinking/effort params. AgentSDKProvider never sets them, so this
    # alias is safe there; openrouter_id is unverified since this phase
    # only exercises agent_sdk.
    "claude-haiku-4-5": ModelSpec(
        alias="claude-haiku-4-5",
        context_window=200_000,
        anthropic_id="claude-haiku-4-5-20251001",
        openrouter_id="anthropic/claude-haiku-4.5",
    ),
}


def resolve(alias: str) -> ModelSpec:
    try:
        return MODEL_REGISTRY[alias]
    except KeyError:
        known = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(f"unknown model alias {alias!r}; known aliases: {known}") from None
