"""LLM utility functions for Vicoa platform.

Session-title generation: OpenRouter-routed DeepSeek v3.2 first, then
Gemini-flash-lite, then Anthropic Haiku 4.5 (direct SDK) as the last resort
for deployments that only set ANTHROPIC_API_KEY. See
`plans/todos/bench-title-models-results.md` for the benchmark that chose this
chain.
"""

import logging

import anthropic

from shared.config import settings
from shared.llms.openrouter import (
    _TITLE_PROMPT,
    _parse_title_json,
    generate_title_via_openrouter,
)

logger = logging.getLogger(__name__)


# OpenRouter slugs for the title chain. Both were chosen by the 2026-05-31
# benchmark: 100% reliability on the test set, latency comparable to Anthropic
# Haiku, and ~5× cheaper per call than Haiku 4.5.
_OPENROUTER_PRIMARY = "deepseek/deepseek-v3.2"
_OPENROUTER_SECONDARY = "google/gemini-3.1-flash-lite"

# Anthropic model for the last-resort path. `claude-3-5-haiku-latest` was
# retired on 2026-02-19 — using the Haiku 4.5 successor.
_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


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
    """Primary title provider: DeepSeek v3.2."""
    return _call_openrouter_title(user_message, model=_OPENROUTER_PRIMARY)


def _call_openrouter_gemini_title(user_message: str) -> str | None:
    """Second title provider: Google Gemini 3.1 Flash Lite."""
    return _call_openrouter_title(user_message, model=_OPENROUTER_SECONDARY)


def _call_anthropic_title(user_message: str) -> str | None:
    """Last-resort title provider: Anthropic Haiku 4.5. None on any failure."""
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


def generate_conversation_title(user_message: str) -> str | None:
    """Generate a short session title from `user_message` via a provider chain.

    Order: OpenRouter DeepSeek v3.2 → OpenRouter Gemini 3.1 Flash Lite →
    Anthropic Haiku 4.5 (direct SDK). Returns None if every provider is
    unconfigured or fails — callers leave `instance.name` NULL so the UI
    keeps its fallback (`latest_message` on web, `agent_type_name` on mobile).
    """
    providers = (
        _call_openrouter_deepseek_title,
        _call_openrouter_gemini_title,
        _call_anthropic_title,
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
