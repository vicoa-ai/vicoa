"""LLM utility functions for Vicoa platform.

Session-title generation: tries Anthropic Haiku 4.5 first (direct SDK),
then falls back to OpenRouter-routed DeepSeek v3.2, then Gemini-flash-lite.
See `plans/todos/bench-title-models-results.md` for the benchmark that
chose this chain.
"""

import json
import logging
import re

import anthropic

from shared.config import settings
from shared.llms.openrouter import generate_title_via_openrouter

logger = logging.getLogger(__name__)


# Anthropic model used for the primary path. `claude-3-5-haiku-latest` was
# retired on 2026-02-19 — using the Haiku 4.5 successor.
_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

# OpenRouter slugs for the fallback chain. Both were chosen by the
# 2026-05-31 benchmark: 100% reliability on the test set, latency comparable
# to Anthropic Haiku, and ~5× cheaper per call than Haiku 4.5.
_OPENROUTER_FALLBACK_PRIMARY = "deepseek/deepseek-v3.2"
_OPENROUTER_FALLBACK_SECONDARY = "google/gemini-3.1-flash-lite"

# No server-side char cap: a hard limit makes the LLM chase the boundary and
# the cut lands mid-word ("Refactor auth middlew…"). Asking for a concise
# title and trusting the LLM produces clean, fully-worded results.
_TITLE_PROMPT = """Generate a short descriptive title for a coding session that just started with this user message. Reply with JSON only, no prose, in the form {{"title": "..."}}. Aim for a concise title (a few words) that captures the user's intent. Write the title in the same language as the user's message; if the language is unclear, use English.

User message:
{message}"""


_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def _parse_title_json(raw: str) -> str | None:
    """Parse a `{"title": "..."}` payload.

    Anthropic's Haiku 4.5+ models wrap JSON output in markdown code fences
    (```json ... ```) even when the prompt asks for raw JSON; strip them
    before parsing. OpenRouter's JSON-mode pass-through doesn't wrap, so
    the strip is a no-op for those.

    Titles are returned verbatim — the prompt steers the LLM toward a few
    words, and any hard server-side cap would just chop a partial word
    (the exact issue this used to have at MAX_AUTO_TITLE_CHARS=40).
    """
    cleaned = raw.strip()
    fence_match = _FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None
    title = payload.get("title") if isinstance(payload, dict) else None
    if not isinstance(title, str):
        return None
    title = title.strip()
    if not title:
        return None
    return title


def _call_anthropic_title(user_message: str) -> str | None:
    """Generate a session title via Anthropic Haiku 4.5. None on any failure."""
    if not settings.anthropic_api_key:
        return None
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        messages: list[anthropic.types.MessageParam] = [
            {"role": "user", "content": _TITLE_PROMPT.format(message=user_message)}
        ]
        # anthropic 1.0.0 removed the `temperature` param from messages.create;
        # titles use the model default. Determinism isn't critical here.
        response = client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=60,
            messages=messages,
        )
        content = response.content[0]
        if isinstance(content, anthropic.types.TextBlock):
            return _parse_title_json(content.text.strip())
        return None
    except Exception as e:
        logger.warning(f"Anthropic title generation failed: {e}")
        return None


def _call_openrouter_title(user_message: str, *, model: str) -> str | None:
    """Generate a title via an OpenRouter-routed model. None on any failure."""
    if not settings.openrouter_api_key:
        return None
    try:
        result = generate_title_via_openrouter(
            user_message,
            model=model,
            max_tokens=60,
            include_usage_cost=False,
        )
    except Exception as e:
        logger.warning(f"OpenRouter title generation via {model} failed: {e}")
        return None
    if result.error:
        logger.warning(
            f"OpenRouter title generation via {model} failed: {result.error}"
        )
        return None
    return result.title


def _call_openrouter_deepseek_title(user_message: str) -> str | None:
    """OpenRouter fallback 1: DeepSeek v3.2."""
    return _call_openrouter_title(user_message, model=_OPENROUTER_FALLBACK_PRIMARY)


def _call_openrouter_gemini_title(user_message: str) -> str | None:
    """OpenRouter fallback 2: Google Gemini 3.1 Flash Lite."""
    return _call_openrouter_title(user_message, model=_OPENROUTER_FALLBACK_SECONDARY)


def generate_conversation_title(user_message: str) -> str | None:
    """Generate a short session title from `user_message` via a provider chain.

    Order: Anthropic Haiku 4.5 (direct SDK) → OpenRouter DeepSeek v3.2 →
    OpenRouter Gemini 3.1 Flash Lite. Returns None if every provider is
    unconfigured or fails — callers leave `instance.name` NULL so the UI
    keeps its fallback (`latest_message` on web, `agent_type_name` on mobile).
    """
    providers = (
        _call_anthropic_title,
        _call_openrouter_deepseek_title,
        _call_openrouter_gemini_title,
    )
    for provider in providers:
        name = getattr(provider, "__name__", repr(provider))
        try:
            title = provider(user_message)
        except Exception as e:
            logger.warning(f"Title provider {name} raised: {e}")
            continue
        if title:
            logger.info(f"Generated title via {name}: {title}")
            return title
    return None
