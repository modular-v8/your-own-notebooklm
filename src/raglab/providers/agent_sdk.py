"""Claude Agent SDK provider: runs the local Claude Code CLI as a subprocess.

Authenticates against the user's existing subscription credential — no API
key. Local personal use only; this is a licensing boundary, not a technical
one (the CLI checks it independently).

The CLI has no exposed token-counting endpoint reachable without an API key,
so over-context detection here uses the same conservative character-based
estimate as OpenRouterProvider, flagged approximate for the same reason.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
)
from claude_agent_sdk import tool as sdk_tool
from claude_agent_sdk import query as sdk_query

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
    split_system,
)
from .models import resolve
from .openrouter import CHARS_PER_TOKEN_ESTIMATE

TOOL_SERVER_NAME = "raglab_tools"
AUTH_HINT = "claude CLI on PATH and authenticated (run `claude login`)"


def is_cli_available() -> bool:
    return shutil.which("claude") is not None


def _flatten(messages: list[Message]) -> str:
    # query() takes one prompt string with no multi-turn history to replay;
    # a one-shot completion has nothing to reconstruct, so prior (non-system)
    # turns are concatenated with role labels instead.
    parts = []
    for m in messages:
        parts.append(m.content if m.role == "user" else f"[{m.role}]\n{m.content}")
    return "\n\n".join(parts)


def _usage_from_result(message: ResultMessage) -> Usage:
    raw = message.usage or {}
    # Anthropic's usage splits input into three counters (fresh, cache-write,
    # cache-read) that must be summed for the true total tokens billed.
    input_tokens = (
        raw.get("input_tokens", 0)
        + raw.get("cache_creation_input_tokens", 0)
        + raw.get("cache_read_input_tokens", 0)
    )
    return Usage(input_tokens, raw.get("output_tokens", 0))


def _build_tool_server(tools: list[ToolSpec], sink: list[ToolCallRecord]):
    sdk_tools = []
    for spec in tools:

        async def handler(args: dict, _spec: ToolSpec = spec) -> dict:
            output = await _spec.handler(args)
            sink.append(ToolCallRecord(_spec.name, args, output))
            return {"content": [{"type": "text", "text": str(output)}]}

        sdk_tools.append(sdk_tool(spec.name, spec.description, spec.input_schema)(handler))
    return create_sdk_mcp_server(TOOL_SERVER_NAME, tools=sdk_tools)


class AgentSDKProvider:
    name = "agent_sdk"

    def __init__(self, model_alias: str):
        if not is_cli_available():
            raise ProviderAuthError("agent_sdk", AUTH_HINT)
        self._spec = resolve(model_alias)
        self.model = self._spec.anthropic_id
        self.context_window = self._spec.context_window

    def _options(
        self, system: str | None, tools: list[ToolSpec] | None, sink: list[ToolCallRecord]
    ) -> ClaudeAgentOptions:
        # setting_sources=[] and strict_mcp_config=True keep this call isolated
        # from the interactive CLI's own defaults: without them, the CLI loads
        # the user's project/user CLAUDE.md and every globally-configured MCP
        # server (mail, calendar, ...) as fresh, uncached context on every
        # single call — tens of thousands of token-cost tokens and real
        # rate-limit quota for a call that should be a clean, minimal baseline.
        base = dict(
            model=self.model,
            tools=[],
            system_prompt=system,
            setting_sources=[],
            strict_mcp_config=True,
        )
        if not tools:
            return ClaudeAgentOptions(**base, max_turns=1)

        server = _build_tool_server(tools, sink)
        allowed = [f"mcp__{TOOL_SERVER_NAME}__{t.name}" for t in tools]
        return ClaudeAgentOptions(
            **base,
            mcp_servers={TOOL_SERVER_NAME: server},
            allowed_tools=allowed,
            max_turns=DEFAULT_TOOL_LOOP_LIMIT,
        )

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,  # unused: ClaudeAgentOptions has no output-length cap
    ) -> Completion:
        system, rest = split_system(messages)
        tool_calls: list[ToolCallRecord] = []
        options = self._options(system, tools, tool_calls)
        prompt = _flatten(rest)
        last_text = ""
        stop_reason = "end_turn"
        usage = Usage(0, 0)

        try:
            async for message in sdk_query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    text_blocks = [b.text for b in message.content if isinstance(b, TextBlock)]
                    if text_blocks:
                        last_text = "".join(text_blocks)
                    stop_reason = message.stop_reason or stop_reason
                elif isinstance(message, ResultMessage):
                    usage = _usage_from_result(message)
        except ClaudeSDKError as exc:
            raise ProviderAuthError("agent_sdk", AUTH_HINT) from exc

        return Completion(
            text=last_text,
            stop_reason=stop_reason,
            usage=usage,
            tool_calls=tuple(tool_calls),
            request_params={"model": self.model},
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> AsyncIterator[Chunk]:
        system, rest = split_system(messages)
        options = self._options(system, tools, [])
        options.include_partial_messages = True
        prompt = _flatten(rest)

        try:
            async for message in sdk_query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            yield Chunk(text=block.text)
            yield Chunk(text="", done=True)
        except ClaudeSDKError as exc:
            raise ProviderAuthError("agent_sdk", AUTH_HINT) from exc

    async def count_tokens(self, messages: list[Message]) -> int:
        total_chars = sum(len(m.content) for m in messages)
        return int(total_chars / CHARS_PER_TOKEN_ESTIMATE)

    async def check_over_context(self, messages: list[Message]) -> None:
        count = await self.count_tokens(messages)
        if count > self.context_window:
            raise OverContextError("agent_sdk", count, self.context_window, approximate=True)
