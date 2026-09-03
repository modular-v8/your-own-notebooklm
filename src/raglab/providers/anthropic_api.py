"""Anthropic API provider: direct Messages API access via ANTHROPIC_API_KEY."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import anthropic

from .base import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TOOL_LOOP_LIMIT,
    Chunk,
    Completion,
    Message,
    OverContextError,
    ProviderAuthError,
    ToolCallRecord,
    ToolSpec,
    Usage,
)
from .models import resolve


def _split_system(messages: list[Message]) -> tuple[str | None, list[Message]]:
    if messages and messages[0].role == "system":
        return messages[0].content, messages[1:]
    return None, messages


def _to_api_messages(messages: list[Message]) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]


def _to_api_tools(tools: list[ToolSpec]) -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in tools
    ]


class AnthropicProvider:
    """Talks to Anthropic's Messages API directly.

    Server-side refusal fallback (auto-rerouting a refused request to another
    model) is never opted into here — a silent mid-run model swap would
    corrupt the eval harness's ruler.
    """

    name = "anthropic"

    def __init__(self, model_alias: str):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderAuthError("anthropic", "ANTHROPIC_API_KEY")
        self._spec = resolve(model_alias)
        self.model = self._spec.anthropic_id
        self.context_window = self._spec.context_window
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Completion:
        system, rest = _split_system(messages)
        api_messages = _to_api_messages(rest)
        tools_by_name = {t.name: t for t in (tools or [])}
        api_tools = _to_api_tools(tools or [])
        tool_calls: list[ToolCallRecord] = []
        total_input = 0
        total_output = 0

        for _ in range(DEFAULT_TOOL_LOOP_LIMIT):
            kwargs: dict = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": api_messages,
            }
            if system is not None:
                kwargs["system"] = system
            if api_tools:
                kwargs["tools"] = api_tools

            try:
                response = await self._client.messages.create(**kwargs)
            except anthropic.AuthenticationError as exc:
                raise ProviderAuthError("anthropic", "ANTHROPIC_API_KEY") from exc

            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            if response.stop_reason != "tool_use" or not tools_by_name:
                text = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                return Completion(
                    text=text,
                    stop_reason=response.stop_reason or "end_turn",
                    usage=Usage(total_input, total_output),
                    tool_calls=tuple(tool_calls),
                    request_params=kwargs,
                )

            api_messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                spec = tools_by_name[block.name]
                output = await spec.handler(block.input)
                tool_calls.append(ToolCallRecord(block.name, block.input, output))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(output),
                    }
                )
            api_messages.append({"role": "user", "content": tool_results})

        raise RuntimeError(f"anthropic: exceeded {DEFAULT_TOOL_LOOP_LIMIT} tool-call rounds")

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> AsyncIterator[Chunk]:
        system, rest = _split_system(messages)
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": _to_api_messages(rest),
        }
        if system is not None:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _to_api_tools(tools)

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield Chunk(text=text)
                yield Chunk(text="", done=True)
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthError("anthropic", "ANTHROPIC_API_KEY") from exc

    async def count_tokens(self, messages: list[Message]) -> int:
        system, rest = _split_system(messages)
        kwargs: dict = {"model": self.model, "messages": _to_api_messages(rest)}
        if system is not None:
            kwargs["system"] = system
        try:
            result = await self._client.messages.count_tokens(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthError("anthropic", "ANTHROPIC_API_KEY") from exc
        return result.input_tokens

    async def check_over_context(self, messages: list[Message]) -> None:
        count = await self.count_tokens(messages)
        if count > self.context_window:
            raise OverContextError("anthropic", count, self.context_window)
