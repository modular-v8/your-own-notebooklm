"""Resolves configuration into concrete LLMProvider instances.

"auto" provider selection follows the fixed precedence Claude Agent SDK ->
Anthropic API key -> OpenRouter, decided once at startup from credential
*availability* (CLI on PATH, env vars set) — never from a failed call. Once a
provider is selected, a failure never falls back to the next one; it fails
loud and names the provider and missing credential, per spec.
"""

from __future__ import annotations

import os
from typing import Literal

from .agent_sdk import AgentSDKProvider, is_cli_available
from .anthropic_api import AnthropicProvider
from .base import LLMProvider, ProviderAuthError
from .openrouter import OpenRouterProvider

ProviderName = Literal["agent_sdk", "anthropic", "openrouter"]

PROVIDER_PRECEDENCE: tuple[ProviderName, ...] = ("agent_sdk", "anthropic", "openrouter")

_CONSTRUCTORS: dict[ProviderName, type] = {
    "agent_sdk": AgentSDKProvider,
    "anthropic": AnthropicProvider,
    "openrouter": OpenRouterProvider,
}


def _is_available(name: ProviderName) -> bool:
    if name == "agent_sdk":
        return is_cli_available()
    if name == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if name == "openrouter":
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    return False


def auto_select() -> ProviderName:
    for name in PROVIDER_PRECEDENCE:
        if _is_available(name):
            return name
    raise ProviderAuthError(
        "auto",
        "no provider available: no `claude` CLI on PATH, no ANTHROPIC_API_KEY, "
        "no OPENROUTER_API_KEY",
    )


def build_provider(name: ProviderName, model_alias: str) -> LLMProvider:
    if name not in _CONSTRUCTORS:
        known = ", ".join(PROVIDER_PRECEDENCE)
        raise ValueError(f"unknown provider {name!r}; known providers: {known}")
    return _CONSTRUCTORS[name](model_alias)
