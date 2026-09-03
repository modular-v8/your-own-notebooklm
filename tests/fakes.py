"""FakeProvider: scripted responses, no network. Every scoring path testable at zero cost."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from raglab.providers.base import Chunk, Completion, Message, OverContextError, ToolSpec, Usage

DEFAULT_CONTEXT_WINDOW = 200_000
CHARS_PER_TOKEN_ESTIMATE = 4

ScriptedResponse = Completion | Callable[[list[Message]], Completion]


class FakeProvider:
    """Replays a fixed sequence of Completions, one per complete() call.

    A response may be a callable taking the request's messages and returning
    a Completion, for tests that need to answer differently depending on the
    prompt (e.g. the judge sending different rubrics for different entries).
    """

    name = "fake"

    def __init__(
        self,
        responses: list[ScriptedResponse],
        *,
        model: str = "fake-model",
        context_window: int = DEFAULT_CONTEXT_WINDOW,
    ):
        self.model = model
        self.context_window = context_window
        self._responses = list(responses)
        self.calls: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 4096,
    ) -> Completion:
        self.calls.append(messages)
        if not self._responses:
            raise AssertionError("FakeProvider: no more scripted responses")
        response = self._responses.pop(0)
        return response(messages) if callable(response) else response

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[Chunk]:
        completion = await self.complete(messages, tools=tools, max_tokens=max_tokens)
        yield Chunk(text=completion.text)
        yield Chunk(text="", done=True)

    async def count_tokens(self, messages: list[Message]) -> int:
        return sum(len(m.content) for m in messages) // CHARS_PER_TOKEN_ESTIMATE

    async def check_over_context(self, messages: list[Message]) -> None:
        count = await self.count_tokens(messages)
        if count > self.context_window:
            raise OverContextError("fake", count, self.context_window)


def text_completion(
    text: str,
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 10,
) -> Completion:
    return Completion(text=text, stop_reason=stop_reason, usage=Usage(input_tokens, output_tokens))
