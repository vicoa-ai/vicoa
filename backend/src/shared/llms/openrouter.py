"""OpenRouter client — single-key gateway to many LLM providers.

OpenRouter speaks the OpenAI Chat Completions API, so we use the `openai`
SDK pointed at `https://openrouter.ai/api/v1`. Authentication is a single
key (`settings.openrouter_api_key`); model selection happens per-call via
the `model` param (e.g. `"anthropic/claude-3.5-haiku"`,
`"deepseek/deepseek-chat"`).

This module is reusable across LLM features (titles, summaries, classification).
The session-title-specific helper `generate_title_via_openrouter` lives here too
— production wires it as the OpenRouter-routed fallback chain (DeepSeek v3.2 →
Gemini-flash-lite) in `shared.llms.utils.generate_conversation_title`.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from shared.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_REFERER = "https://vicoa.ai"
DEFAULT_APP_TITLE = "vicoa-backend"

# Reuse the same prompt template + char cap as shared.llms.utils so titles
# generated via OpenRouter are directly comparable to titles from the
# direct-provider path.
_TITLE_PROMPT = """Generate a short descriptive title for a coding session that just started with this user message. Reply with JSON only, no prose, in the form {{"title": "..."}}. The title must be <= 40 chars and capture the user's intent.

User message:
{message}"""

MAX_AUTO_TITLE_CHARS = 40


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


def _build_client(api_key: str | None = None, *, app_title: str = DEFAULT_APP_TITLE):
    """Construct an `openai.OpenAI` client pointed at OpenRouter.

    Imported lazily so the module loads even if `openai` isn't installed
    in environments that don't need OpenRouter (e.g. minimal CI).
    """
    import openai

    resolved_key = api_key or settings.openrouter_api_key
    if not resolved_key:
        raise ValueError(
            "OPENROUTER_API_KEY not configured. Set it in .env or pass api_key=."
        )
    return openai.OpenAI(
        api_key=resolved_key,
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
) -> OpenRouterResult:
    """Generic single-shot OpenRouter chat completion.

    Never raises for API/network/parse errors — populates `error` instead.
    `json_mode=True` sets `response_format={"type": "json_object"}` for
    models that honor it (DeepSeek, GPT, Claude all support it).
    `include_usage_cost=True` asks OpenRouter to attach the request's USD
    cost to `usage.cost` — only useful when you want to track spend.
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
    if include_usage_cost:
        kwargs["extra_body"] = {"usage": {"include": True}}

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


def _parse_title_json(raw: str | None) -> str | None:
    """Parse `{"title": "..."}` payload, capped at MAX_AUTO_TITLE_CHARS.

    Mirrors `shared.llms.utils._parse_title_json` so OpenRouter-routed titles
    behave identically to direct-provider titles. Strips markdown fences
    first since Anthropic's newer models wrap JSON output.
    """
    if raw is None:
        return None
    cleaned = _strip_markdown_fence(raw)
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    title = payload.get("title")
    if not isinstance(title, str):
        return None
    title = title.strip()
    if not title:
        return None
    return title[:MAX_AUTO_TITLE_CHARS]


@dataclass
class TitleResult:
    """Outcome of one title-gen call. Convenient for benchmarking."""

    title: str | None
    raw_text: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: int
    error: str | None = None

    @property
    def parsed(self) -> bool:
        return self.title is not None


def generate_title_via_openrouter(
    user_message: str,
    *,
    model: str = "anthropic/claude-3.5-haiku",
    api_key: str | None = None,
    include_usage_cost: bool = True,
    max_tokens: int = 60,
) -> TitleResult:
    """Generate a session title for `user_message` via the given OpenRouter model.

    Uses the same prompt and char cap as production (`shared.llms.utils`).
    Suitable both for benchmarking different models and (eventually) for
    swapping the production direct-provider path to OpenRouter if a
    cheaper model proves good enough.

    `max_tokens` controls the per-call output budget; bump it (e.g. 300) when
    benchmarking reasoning/thinking models that consume budget on hidden
    chain-of-thought before emitting JSON.
    """
    result = call_openrouter(
        model=model,
        prompt=_TITLE_PROMPT.format(message=user_message),
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=0.3,
        json_mode=True,
        include_usage_cost=include_usage_cost,
    )

    return TitleResult(
        title=_parse_title_json(result.text) if result.ok else None,
        raw_text=result.text,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        error=result.error,
    )
