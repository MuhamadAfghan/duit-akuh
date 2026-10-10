"""Adapter for the self-hosted `lumi-ai` service (PRD section 13).

vLLM exposes an OpenAI-compatible API, so this is a thin client over
``POST /v1/chat/completions``.

**Requests are streamed.** Not for UI smoothness — Cloudflare returns 524
if a response has not *started* within 100 seconds, and a queued
generation on a shared GPU can easily exceed that before its first
token. Streaming makes the first byte arrive promptly, which is what
keeps the tunnel from dropping the request. The deltas are accumulated
here and returned as one result; streaming to the browser is a separate
concern layered on top.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from .base import AiBadResponse, AiError, AiTimeout, ChatResult, ToolCall, Usage

#: Cloudflare drops a request whose response has not begun within 100s.
#: Staying under that lets us return a clear error instead of a 524 the
#: user cannot interpret.
CONNECT_TIMEOUT = 10.0
FIRST_BYTE_TIMEOUT = 90.0
#: Generous: once bytes are flowing the tunnel is satisfied, and a long
#: analysis answer legitimately takes a while.
TOTAL_TIMEOUT = 300.0


class OpenAiCompatAdapter:
    """Talks to vLLM (and would talk to Ollama or a cloud model unchanged)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(TOTAL_TIMEOUT, connect=CONNECT_TIMEOUT, read=FIRST_BYTE_TIMEOUT)
        )

    def _payload(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        enable_thinking: bool,
        temperature: float,
        max_tokens: int | None,
        json_object: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "temperature": temperature,
            "stream": True,
            # Usage is omitted from streamed responses unless asked for,
            # and the PRD requires token counts in the AI request log.
            "stream_options": {"include_usage": True},
            # Reasoning off by default: slower, and the PRD specifies it
            # stays off for drafts and receipt extraction.
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
        }

        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if json_object:
            payload["response_format"] = {"type": "json_object"}

        return payload

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
        payload = self._payload(
            messages=messages,
            tools=tools,
            enable_thinking=enable_thinking,
            temperature=temperature,
            max_tokens=max_tokens,
            json_object=json_object,
        )

        client = self._client or self._build_client()
        owns_client = self._client is None
        started = time.monotonic()

        try:
            return await self._stream(client, payload, on_delta)
        except httpx.TimeoutException as exc:
            raise AiTimeout(
                f"Layanan AI tidak merespons dalam {time.monotonic() - started:.0f} detik"
            ) from exc
        except httpx.HTTPError as exc:
            raise AiError(f"Layanan AI tidak dapat dihubungi: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def _stream(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        on_delta: Callable[[str], None] | None = None,
    ) -> ChatResult:
        content_parts: list[str] = []
        # Tool calls arrive as deltas keyed by index, with the name in one
        # chunk and the arguments dribbled across later ones.
        partial_tools: dict[int, dict[str, Any]] = {}
        usage = Usage()
        model = self._model

        async with client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")[:400]
                raise AiError(f"Layanan AI menolak permintaan ({response.status_code}): {body}")

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue

                data = line[len("data:") :].strip()

                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise AiBadResponse(f"Potongan stream bukan JSON: {data[:120]}") from exc

                model = chunk.get("model") or model

                if chunk.get("usage"):
                    usage = Usage(
                        prompt_tokens=chunk["usage"].get("prompt_tokens"),
                        completion_tokens=chunk["usage"].get("completion_tokens"),
                    )

                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}

                    if delta.get("content"):
                        content_parts.append(delta["content"])

                        if on_delta is not None:
                            on_delta(delta["content"])

                    for call in delta.get("tool_calls") or []:
                        _accumulate_tool_call(partial_tools, call)

        return ChatResult(
            content="".join(content_parts),
            tool_calls=_finish_tool_calls(partial_tools),
            usage=usage,
            model=model,
        )


def _accumulate_tool_call(partial: dict[int, dict[str, Any]], call: dict[str, Any]) -> None:
    index = call.get("index", 0)
    slot = partial.setdefault(index, {"id": "", "name": "", "arguments": ""})

    if call.get("id"):
        slot["id"] = call["id"]

    function = call.get("function") or {}

    if function.get("name"):
        slot["name"] = function["name"]

    if function.get("arguments"):
        slot["arguments"] += function["arguments"]


def _finish_tool_calls(partial: dict[int, dict[str, Any]]) -> list[ToolCall]:
    calls = []

    for index in sorted(partial):
        slot = partial[index]

        if not slot["name"]:
            continue

        raw = slot["arguments"].strip() or "{}"

        try:
            arguments = json.loads(raw)
        except json.JSONDecodeError as exc:
            # A truncated or malformed argument object is the model's
            # fault, not the user's. Surfacing it as a clear error lets
            # the orchestrator retry once and then fall back to manual
            # entry, rather than posting something half-parsed.
            raise AiBadResponse(
                f"Argumen tool '{slot['name']}' bukan JSON yang valid: {raw[:160]}"
            ) from exc

        if not isinstance(arguments, dict):
            raise AiBadResponse(f"Argumen tool '{slot['name']}' bukan objek JSON")

        calls.append(
            ToolCall(id=slot["id"] or f"call_{index}", name=slot["name"], arguments=arguments)
        )

    return calls
