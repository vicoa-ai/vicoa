"""OpenRouter client — single-key gateway to many LLM providers.

OpenRouter speaks the OpenAI Chat Completions API, so we use the `openai`
SDK pointed at `https://openrouter.ai/api/v1`. Authentication is a single
key (`settings.openrouter_api_key`); model selection happens per-call via
the `model` param (e.g. `"anthropic/claude-3.5-haiku"`,
`"deepseek/deepseek-chat"`).

This module is reusable across LLM features (titles, summaries, classification).
Session titles and worktree names live in `shared.llms.session_names`.
"""

from __future__ import annotations

import functools
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from shared.config import settings

if TYPE_CHECKING:
    import openai

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_REFERER = "https://vicoa.ai"
DEFAULT_APP_TITLE = "vicoa-backend"


@dataclass
class OpenRouterResult:
    """Result of one OpenRouter completion call.

    `text` is the raw assistant message string; callers handle their own
    parsing (e.g. JSON-mode responses). `cost_usd` is OpenRouter's own
    accounting (returned only when the request opted in via
    `extra_body={"usage": {"include": True}}`).
    """

    text: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.text is not None


def _build_client(
    api_key: str | None = None, *, app_title: str = DEFAULT_APP_TITLE
) -> openai.OpenAI:
    """The `openai.OpenAI` client pointed at OpenRouter for this key.

    Imported lazily so the module loads even if `openai` isn't installed
    in environments that don't need OpenRouter (e.g. minimal CI).
    """
    resolved_key = api_key or settings.openrouter_api_key
    if not resolved_key:
        raise ValueError(
            "OPENROUTER_API_KEY not configured. Set it in .env or pass api_key=."
        )
    return _client_for(resolved_key, app_title)


# One client per key, reused across calls (the client is thread-safe): a new
# one opens a new connection to OpenRouter each call, which cost about 0.1s a
# call, out of the 1s a new worktree waits for its name.
@functools.lru_cache(maxsize=8)
def _client_for(api_key: str, app_title: str) -> openai.OpenAI:
    import openai

    return openai.OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": DEFAULT_REFERER,
            "X-Title": app_title,
        },
    )


def call_openrouter(
    model: str,
    prompt: str,
    *,
    api_key: str | None = None,
    system_prompt: str | None = None,
    max_tokens: int = 60,
    temperature: float = 0.3,
    json_mode: bool = False,
    include_usage_cost: bool = False,
    app_title: str = DEFAULT_APP_TITLE,
    extra_body: dict[str, Any] | None = None,
    request_timeout: float | None = None,
) -> OpenRouterResult:
    """Generic single-shot OpenRouter chat completion.

    Never raises for API/network/parse errors — populates `error` instead.
    `json_mode=True` sets `response_format={"type": "json_object"}` for
    models that honor it (DeepSeek, GPT, Claude all support it).
    `include_usage_cost=True` asks OpenRouter to attach the request's USD
    cost to `usage.cost` — only useful when you want to track spend.
    `extra_body` carries OpenRouter-specific request fields (`provider`
    routing, `reasoning` effort); `request_timeout` bounds this one call,
    which otherwise inherits the SDK's 10-minute default.
    """
    try:
        client = _build_client(api_key, app_title=app_title)
    except ValueError as exc:
        return OpenRouterResult(
            text=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=None,
            latency_ms=0,
            error=str(exc),
        )

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    body: dict[str, Any] = dict(extra_body or {})
    if include_usage_cost:
        body["usage"] = {"include": True}
    if body:
        kwargs["extra_body"] = body
    if request_timeout is not None:
        kwargs["timeout"] = request_timeout

    start = time.perf_counter()
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.warning(f"OpenRouter call to {model} failed: {exc}")
        return OpenRouterResult(
            text=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=None,
            latency_ms=elapsed_ms,
            error=str(exc),
        )

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    text = response.choices[0].message.content if response.choices else None
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    cost_raw = getattr(usage, "cost", None)
    cost_usd = float(cost_raw) if cost_raw is not None else None

    return OpenRouterResult(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=elapsed_ms,
    )


_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def _strip_markdown_fence(raw: str) -> str:
    """Strip ```...``` / ```json ... ``` wrapping if present.

    Anthropic's Haiku 4.5+ models often wrap JSON output in markdown fences
    even when asked for raw JSON. OpenAI's JSON-mode and OpenRouter's
    pass-through generally don't. This normalizes both shapes.
    """
    stripped = raw.strip()
    match = _FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped
