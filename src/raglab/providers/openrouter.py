"""OpenRouter provider: OpenAI-compatible chat completions at OpenRouter's base URL.

OpenRouter has no token-counting endpoint. Over-context detection here uses a
conservative character-based estimate (chars / 3.5, which undercounts real
tokens for English prose) and is flagged approximate — it can refuse a
document that would in fact have fit, which is the correct direction to err.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import openai

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

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CHARS_PER_TOKEN_ESTIMATE = 3.5


def _to_api_messages(messages: list[Message]) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]


def _to_api_tools(tools: list[ToolSpec]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


class OpenRouterProvider:
    """Talks to OpenRouter's OpenAI-compatible /chat/completions endpoint."""

    name = "openrouter"

    def __init__(self, model_alias: str):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ProviderAuthError("openrouter", "OPENROUTER_API_KEY")
        self._spec = resolve(model_alias)
        self.model = self._spec.openrouter_id
        self.context_window = self._spec.context_window
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Completion:
        api_messages = _to_api_messages(messages)
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
            if api_tools:
                kwargs["tools"] = api_tools

            try:
                response = await self._client.chat.completions.create(**kwargs)
            except openai.AuthenticationError as exc:
                raise ProviderAuthError("openrouter", "OPENROUTER_API_KEY") from exc

            choice = response.choices[0]
            if response.usage is not None:
                total_input += response.usage.prompt_tokens
                total_output += response.usage.completion_tokens

            calls = choice.message.tool_calls or []
            if not calls or not tools_by_name:
                return Completion(
                    text=choice.message.content or "",
                    stop_reason=choice.finish_reason or "stop",
                    usage=Usage(total_input, total_output),
                    tool_calls=tuple(tool_calls),
                    request_params=kwargs,
                )

            api_messages.append(
                {
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.function.name, "arguments": call.function.arguments},
                        }
                        for call in calls
                    ],
                }
            )
            for call in calls:
                spec = tools_by_name[call.function.name]
                args = json.loads(call.function.arguments)
                output = await spec.handler(args)
                tool_calls.append(ToolCallRecord(call.function.name, args, output))
                api_messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": str(output)}
                )

        raise RuntimeError(f"openrouter: exceeded {DEFAULT_TOOL_LOOP_LIMIT} tool-call rounds")

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> AsyncIterator[Chunk]:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": _to_api_messages(messages),
            "stream": True,
        }
        if tools:
            kwargs["tools"] = _to_api_tools(tools)

        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for event in stream:
                delta = event.choices[0].delta.content if event.choices else None
                if delta:
                    yield Chunk(text=delta)
            yield Chunk(text="", done=True)
        except openai.AuthenticationError as exc:
            raise ProviderAuthError("openrouter", "OPENROUTER_API_KEY") from exc

    async def count_tokens(self, messages: list[Message]) -> int:
        total_chars = sum(len(m.content) for m in messages)
        return int(total_chars / CHARS_PER_TOKEN_ESTIMATE)

    async def check_over_context(self, messages: list[Message]) -> None:
        count = await self.count_tokens(messages)
        if count > self.context_window:
            raise OverContextError("openrouter", count, self.context_window, approximate=True)
