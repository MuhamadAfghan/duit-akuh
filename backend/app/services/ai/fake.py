"""A scripted adapter for tests.

Lets the orchestrator be exercised with no network, no GPU and no API
key, and — more usefully — lets tests pin down what happens when the
model misbehaves: bad arguments, an unknown tool, a refusal to stop
calling tools, an outage.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .base import AiError, ChatResult, ToolCall, Usage


class FakeAdapter:
    """Replays a scripted list of turns.

    Each item is either a :class:`ChatResult` or an exception to raise.
    The adapter records the prompts it was given so tests can assert on
    what the orchestrator actually sent — for instance that tool results
    were fed back in the right shape.
    """

    def __init__(self, script: list[ChatResult | Exception] | None = None) -> None:
        self.script: list[ChatResult | Exception] = list(script or [])
        self.calls: list[dict[str, Any]] = []

    def queue(self, item: ChatResult | Exception) -> None:
        self.script.append(item)

    async def chat(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_object: bool = False,
        on_delta: Callable[[str], None] | None = None,
    ) -> ChatResult:
        self.calls.append(
            {
                "messages": [dict(m) for m in messages],
                "tools": [t["function"]["name"] for t in (tools or [])],
                "enable_thinking": enable_thinking,
                "temperature": temperature,
            }
        )

        if not self.script:
            return ChatResult(content="(fake: skrip habis)", model="fake")

        item = self.script.pop(0)

        if isinstance(item, Exception):
            raise item

        # Emit the scripted content in a couple of pieces so streaming
        # consumers are exercised rather than seeing one lump.
        if on_delta is not None and item.content:
            middle = max(1, len(item.content) // 2)
            on_delta(item.content[:middle])
            on_delta(item.content[middle:])

        return item


def text(content: str) -> ChatResult:
    return ChatResult(content=content, usage=Usage(10, 5), model="fake")


def tool(name: str, arguments: dict[str, Any], *, content: str = "") -> ChatResult:
    return ChatResult(
        content=content,
        tool_calls=[ToolCall(id=f"call_{name}", name=name, arguments=arguments)],
        usage=Usage(10, 5),
        model="fake",
    )


def outage(message: str = "lumi-ai tidak dapat dihubungi") -> AiError:
    return AiError(message)
