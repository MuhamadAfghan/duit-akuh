"""The lumi-ai adapter's wire behaviour, against a mock transport.

No network and no API key needed, but this is the only place that pins
down what we actually send to vLLM and how we read it back — in
particular that requests are streamed, that `enable_thinking` is off by
default, and that tool-call arguments split across chunks are
reassembled correctly. Those are easy to get subtly wrong and impossible
to notice from a fake adapter.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.ai.base import AiBadResponse, AiError, AiTimeout
from app.services.ai.openai_compat import OpenAiCompatAdapter

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def sse(*chunks: dict) -> bytes:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return (body + "data: [DONE]\n\n").encode()


def adapter_with(handler) -> tuple[OpenAiCompatAdapter, dict]:
    """Build an adapter whose transport records the request it was given."""
    captured: dict = {}

    def intercept(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(intercept))
    adapter = OpenAiCompatAdapter(
        base_url="https://llm.example.com/v1",
        api_key="secret-key",
        model="qwen3.5-9b",
        client=client,
    )
    return adapter, captured


async def test_request_is_streamed_with_thinking_off(anyio_backend):
    """Streaming is not cosmetic: Cloudflare 524s if the response has not
    started within 100s, and a queued generation easily exceeds that."""
    adapter, captured = adapter_with(
        lambda r: httpx.Response(200, content=sse({"choices": [{"delta": {"content": "halo"}}]}))
    )

    result = await adapter.chat(messages=[{"role": "user", "content": "hai"}])

    assert captured["payload"]["stream"] is True
    assert captured["payload"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["payload"]["temperature"] == 0.0
    assert captured["payload"]["stream_options"] == {"include_usage": True}
    assert captured["payload"]["model"] == "qwen3.5-9b"
    assert captured["url"] == "https://llm.example.com/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer secret-key"
    assert result.content == "halo"


async def test_content_deltas_are_joined(anyio_backend):
    adapter, _ = adapter_with(
        lambda r: httpx.Response(
            200,
            content=sse(
                {"choices": [{"delta": {"content": "Saldo "}}]},
                {"choices": [{"delta": {"content": "kamu "}}]},
                {"choices": [{"delta": {"content": "Rp1.000."}}]},
            ),
        )
    )

    result = await adapter.chat(messages=[])

    assert result.content == "Saldo kamu Rp1.000."


async def test_tool_call_arguments_split_across_chunks_are_reassembled(anyio_backend):
    """vLLM dribbles the argument JSON out a few characters at a time."""
    adapter, _ = adapter_with(
        lambda r: httpx.Response(
            200,
            content=sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_1",
                                        "function": {"name": "propose_transactions"},
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "function": {"arguments": '{"transactions":'}}
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": '[{"amount":35000}]}'},
                                    }
                                ]
                            }
                        }
                    ]
                },
            ),
        )
    )

    result = await adapter.chat(messages=[])

    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.id == "call_1"
    assert call.name == "propose_transactions"
    assert call.arguments == {"transactions": [{"amount": 35000}]}


async def test_parallel_tool_calls_are_kept_apart(anyio_backend):
    adapter, _ = adapter_with(
        lambda r: httpx.Response(
            200,
            content=sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "a",
                                        "function": {"name": "get_summary", "arguments": "{}"},
                                    },
                                    {
                                        "index": 1,
                                        "id": "b",
                                        "function": {"name": "get_accounts", "arguments": "{}"},
                                    },
                                ]
                            }
                        }
                    ]
                },
            ),
        )
    )

    result = await adapter.chat(messages=[])

    assert [c.name for c in result.tool_calls] == ["get_summary", "get_accounts"]


async def test_usage_is_captured_for_the_ai_log(anyio_backend):
    adapter, _ = adapter_with(
        lambda r: httpx.Response(
            200,
            content=sse(
                {"choices": [{"delta": {"content": "ok"}}]},
                {"choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 8}},
            ),
        )
    )

    result = await adapter.chat(messages=[])

    assert result.usage.prompt_tokens == 120
    assert result.usage.completion_tokens == 8


async def test_tools_are_only_sent_when_provided(anyio_backend):
    adapter, captured = adapter_with(
        lambda r: httpx.Response(200, content=sse({"choices": [{"delta": {"content": "ok"}}]}))
    )

    await adapter.chat(messages=[])
    assert "tools" not in captured["payload"]

    await adapter.chat(
        messages=[], tools=[{"type": "function", "function": {"name": "get_summary"}}]
    )
    assert captured["payload"]["tool_choice"] == "auto"


async def test_json_object_mode_is_opt_in(anyio_backend):
    """Used for receipt extraction, per PRD section 13."""
    adapter, captured = adapter_with(
        lambda r: httpx.Response(200, content=sse({"choices": [{"delta": {"content": "{}"}}]}))
    )

    await adapter.chat(messages=[], json_object=True)

    assert captured["payload"]["response_format"] == {"type": "json_object"}


async def test_thinking_can_be_enabled_for_analysis(anyio_backend):
    adapter, captured = adapter_with(
        lambda r: httpx.Response(200, content=sse({"choices": [{"delta": {"content": "ok"}}]}))
    )

    await adapter.chat(messages=[], enable_thinking=True)

    assert captured["payload"]["chat_template_kwargs"] == {"enable_thinking": True}


# ----------------------------------------------------------------------
# Failure modes - all must raise AiError so the orchestrator degrades
# ----------------------------------------------------------------------


async def test_http_error_becomes_an_ai_error(anyio_backend):
    adapter, _ = adapter_with(lambda r: httpx.Response(503, text="GPU busy"))

    with pytest.raises(AiError) as excinfo:
        await adapter.chat(messages=[])

    assert "503" in str(excinfo.value)


async def test_unauthorised_becomes_an_ai_error(anyio_backend):
    adapter, _ = adapter_with(lambda r: httpx.Response(401, text="bad key"))

    with pytest.raises(AiError):
        await adapter.chat(messages=[])


async def test_a_timeout_becomes_ai_timeout(anyio_backend):
    def explode(request):
        raise httpx.ReadTimeout("too slow", request=request)

    adapter, _ = adapter_with(explode)

    with pytest.raises(AiTimeout):
        await adapter.chat(messages=[])


async def test_truncated_tool_arguments_raise_rather_than_half_parse(anyio_backend):
    """A cut-off argument object must not become a partial transaction."""
    adapter, _ = adapter_with(
        lambda r: httpx.Response(
            200,
            content=sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "x",
                                        "function": {
                                            "name": "propose_transactions",
                                            "arguments": '{"transactions": [{"amount": 350',
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
            ),
        )
    )

    with pytest.raises(AiBadResponse):
        await adapter.chat(messages=[])


async def test_malformed_stream_chunk_raises(anyio_backend):
    adapter, _ = adapter_with(
        lambda r: httpx.Response(200, content=b"data: {not json}\n\ndata: [DONE]\n\n")
    )

    with pytest.raises(AiBadResponse):
        await adapter.chat(messages=[])


async def test_the_api_key_is_not_in_the_error_text(anyio_backend):
    """An error surfaces to logs and possibly the user; the key must not."""
    adapter, _ = adapter_with(lambda r: httpx.Response(500, text="boom"))

    with pytest.raises(AiError) as excinfo:
        await adapter.chat(messages=[])

    assert "secret-key" not in str(excinfo.value)
