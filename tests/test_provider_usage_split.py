"""Usage cache-split (Phase 5, T1.2/T1.3): fresh/cache_creation/cache_read
recorded alongside the pre-existing summed input_tokens, zero rather than
None when a provider has no breakdown to report.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import ResultMessage

from raglab.providers.agent_sdk import _usage_from_result
from raglab.providers.anthropic_api import AnthropicProvider
from raglab.providers.base import Message
from raglab.providers.openrouter import OpenRouterProvider


def _result_message(usage: dict) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=100,
        is_error=False,
        num_turns=1,
        session_id="s-1",
        usage=usage,
    )


def test_agent_sdk_splits_and_sums_cache_usage():
    message = _result_message(
        {
            "input_tokens": 100,
            "cache_creation_input_tokens": 30,
            "cache_read_input_tokens": 500,
            "output_tokens": 20,
        }
    )
    usage = _usage_from_result(message)

    assert usage.fresh_input_tokens == 100
    assert usage.cache_creation_tokens == 30
    assert usage.cache_read_tokens == 500
    assert usage.output_tokens == 20
    assert usage.input_tokens == usage.fresh_input_tokens + usage.cache_creation_tokens + usage.cache_read_tokens


def test_agent_sdk_zero_cache_fields_when_absent():
    message = _result_message({"input_tokens": 42, "output_tokens": 7})
    usage = _usage_from_result(message)

    assert usage.fresh_input_tokens == 42
    assert usage.cache_creation_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.input_tokens == 42


class _FakeAnthropicUsage:
    def __init__(self, input_tokens, output_tokens, cache_creation_input_tokens=None, cache_read_input_tokens=None):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class _FakeBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _FakeAnthropicResponse:
    def __init__(self, usage, stop_reason: str = "end_turn"):
        self.usage = usage
        self.stop_reason = stop_reason
        self.content = [_FakeBlock("hi")]


@pytest.mark.asyncio
async def test_anthropic_splits_cache_usage_when_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider("claude-sonnet-5")
    provider._client.messages.create = AsyncMock(
        return_value=_FakeAnthropicResponse(
            _FakeAnthropicUsage(100, 20, cache_creation_input_tokens=30, cache_read_input_tokens=50)
        )
    )

    completion = await provider.complete([Message(role="user", content="hi")])

    assert completion.usage.fresh_input_tokens == 100
    assert completion.usage.cache_creation_tokens == 30
    assert completion.usage.cache_read_tokens == 50
    assert completion.usage.input_tokens == 180


@pytest.mark.asyncio
async def test_anthropic_zero_cache_fields_when_absent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider("claude-sonnet-5")
    provider._client.messages.create = AsyncMock(return_value=_FakeAnthropicResponse(_FakeAnthropicUsage(100, 20)))

    completion = await provider.complete([Message(role="user", content="hi")])

    assert completion.usage.fresh_input_tokens == 100
    assert completion.usage.cache_creation_tokens == 0
    assert completion.usage.cache_read_tokens == 0
    assert completion.usage.input_tokens == 100


class _FakeOpenRouterMessage:
    tool_calls = None

    def __init__(self, content: str):
        self.content = content


class _FakeOpenRouterChoice:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.message = _FakeOpenRouterMessage(content)
        self.finish_reason = finish_reason


class _FakeOpenRouterUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeOpenRouterResponse:
    def __init__(self, content: str, prompt_tokens: int, completion_tokens: int):
        self.choices = [_FakeOpenRouterChoice(content)]
        self.usage = _FakeOpenRouterUsage(prompt_tokens, completion_tokens)


@pytest.mark.asyncio
async def test_openrouter_records_full_total_as_fresh_no_cache_breakdown(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    provider = OpenRouterProvider("claude-sonnet-5")
    provider._client.chat.completions.create = AsyncMock(
        return_value=_FakeOpenRouterResponse("hi", prompt_tokens=100, completion_tokens=20)
    )

    completion = await provider.complete([Message(role="user", content="hi")])

    assert completion.usage.input_tokens == 100
    assert completion.usage.fresh_input_tokens == 100
    assert completion.usage.cache_creation_tokens == 0
    assert completion.usage.cache_read_tokens == 0
