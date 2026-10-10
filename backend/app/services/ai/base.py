"""The AI adapter interface (PRD section 13).

The PRD requires an adapter exposing ``chat`` / ``vision`` /
``transcribe`` so the backing model can be swapped for the Ollama
fallback or a cloud provider. Everything above this module talks to the
protocol, never to an HTTP client.

Nothing here computes money. The model's job is to propose a structured
action; the backend validates it and does the arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class AiError(Exception):
    """The AI service failed.

    Always recoverable from the user's point of view: `lumi-ai` is a
    single point of failure with no SLA, so every path that hits it must
    degrade to manual entry rather than blocking the user (AC09/AC22).
    """

    code = "ai_unavailable"


class AiTimeout(AiError):
    code = "ai_timeout"


class AiBadResponse(AiError):
    """The model replied with something that does not fit the contract."""

    code = "ai_bad_response"


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    #: Already parsed from the model's JSON string. Never trusted — the
    #: dispatcher validates every field before it reaches the ledger.
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ChatResult:
    """One assistant turn."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""


@runtime_checkable
class AiAdapter(Protocol):
    """What the orchestrator depends on.

    Implementations: :class:`~.openai_compat.OpenAiCompatAdapter` for the
    real `lumi-ai` service, and :class:`~.fake.FakeAdapter` for tests, so
    the orchestrator can be exercised without a network or a GPU.
    """

    async def chat(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_object: bool = False,
    ) -> ChatResult:
        """Run one turn, returning content and any tool calls.

        ``enable_thinking`` defaults to off: the PRD specifies reasoning
        is disabled for transaction drafts and receipt extraction because
        it is slower, and enabled only for analysis and explanations.
        """
        ...
