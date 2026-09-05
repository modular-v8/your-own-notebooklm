"""LLMProvider protocol: the contract every pipeline and eval component depends on.

Tool calling is resolved *inside* a provider's complete()/stream() call, not by
the caller: a ToolSpec carries its own async handler, and each implementation
runs its own request/execute/respond loop until the model stops calling tools.
This keeps the interface identical across Anthropic, OpenRouter, and the Agent
SDK, where tool execution is inherently owned by the CLI subprocess rather than
handed back to the caller.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]

DEFAULT_MAX_TOKENS = 4096
DEFAULT_TOOL_LOOP_LIMIT = 8


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


def split_system(messages: list[Message]) -> tuple[str | None, list[Message]]:
    """Pull a leading system message out, since most SDKs take it as a
    separate parameter rather than as part of the message list."""
    if messages and messages[0].role == "system":
        return messages[0].content, messages[1:]
    return None, messages


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    input: dict[str, Any]
    output: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Completion:
    text: str
    stop_reason: str
    usage: Usage
    tool_calls: tuple[ToolCallRecord, ...] = ()
    request_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    text: str
    done: bool = False


class OverContextError(RuntimeError):
    """Raised when a document plus prompt exceeds a provider's context window.

    Callers must not truncate and retry — the runner records this as a
    skipped entry, per spec.
    """

    def __init__(self, provider: str, token_count: int, context_window: int, *, approximate: bool = False):
        self.provider = provider
        self.token_count = token_count
        self.context_window = context_window
        self.approximate = approximate
        qualifier = "~" if approximate else ""
        super().__init__(
            f"{provider}: {qualifier}{token_count} tokens exceeds context window "
            f"of {context_window} tokens"
        )


class ProviderAuthError(RuntimeError):
    """Raised when a provider is selected but cannot authenticate.

    Naming the provider and the missing credential is a spec requirement —
    never fall back to another provider on this error.
    """

    def __init__(self, provider: str, missing_credential: str):
        self.provider = provider
        self.missing_credential = missing_credential
        super().__init__(f"{provider}: missing or invalid {missing_credential}")


@runtime_checkable
class LLMProvider(Protocol):
    """A chat-completion backend: one concrete model, reachable one way."""

    name: str
    model: str
    context_window: int

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Completion: ...

    def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> AsyncIterator[Chunk]: ...

    async def count_tokens(self, messages: list[Message]) -> int: ...

    async def check_over_context(self, messages: list[Message]) -> None:
        """Raise OverContextError if messages exceed context_window. Never truncates."""
        ...
