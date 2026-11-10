"""Unit tests for shared.llms.openrouter — single-key multi-provider gateway."""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from shared.llms.openrouter import _client_for, _strip_markdown_fence, call_openrouter


@pytest.fixture(autouse=True)
def _fresh_clients() -> Iterator[None]:
    # Clients are cached per key; each test patches `openai.OpenAI` anew.
    _client_for.cache_clear()
    yield
    _client_for.cache_clear()


def _mock_completion(text: str, *, cost: float | None = None) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    usage = MagicMock()
    usage.prompt_tokens = 120
    usage.completion_tokens = 8
    if cost is not None:
        usage.cost = cost
    else:
        # Simulate openai SDK behavior when OpenRouter omits cost
        del usage.cost
    response.usage = usage
    return response


class TestCallOpenRouter:
    def test_missing_api_key_returns_error_result(self):
        with patch("shared.llms.openrouter.settings") as mock_settings:
            mock_settings.openrouter_api_key = ""
            result = call_openrouter("anthropic/claude-3.5-haiku", "hello")
            assert not result.ok
            assert result.error is not None
            assert "OPENROUTER_API_KEY" in result.error

    def test_explicit_api_key_overrides_settings(self):
        with (
            patch("shared.llms.openrouter.settings") as mock_settings,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            mock_settings.openrouter_api_key = ""
            client = MagicMock()
            client.chat.completions.create.return_value = _mock_completion(
                '{"title": "Hi"}'
            )
            mock_openai_cls.return_value = client

            result = call_openrouter(
                "anthropic/claude-3.5-haiku", "hello", api_key="sk-or-explicit"
            )
            assert result.ok
            mock_openai_cls.assert_called_once()
            assert mock_openai_cls.call_args.kwargs["api_key"] == "sk-or-explicit"
            assert (
                mock_openai_cls.call_args.kwargs["base_url"]
                == "https://openrouter.ai/api/v1"
            )

    def test_reuses_one_client_per_key(self):
        # A new client opens a new connection each call, ~0.1s of the 1s a
        # new worktree waits for its name.
        with (
            patch("shared.llms.openrouter.settings") as mock_settings,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            mock_settings.openrouter_api_key = "sk-or-a"
            mock_openai_cls.return_value.chat.completions.create.return_value = (
                _mock_completion("{}")
            )
            call_openrouter("deepseek/deepseek-v4.1-flash", "one")
            call_openrouter("deepseek/deepseek-v4.1-flash", "two")
            assert mock_openai_cls.call_count == 1

            mock_settings.openrouter_api_key = "sk-or-b"
            call_openrouter("deepseek/deepseek-v4.1-flash", "three")
            assert mock_openai_cls.call_count == 2
            assert mock_openai_cls.call_args.kwargs["api_key"] == "sk-or-b"

    def test_passes_json_mode_and_usage_flags(self):
        with (
            patch("shared.llms.openrouter.settings") as mock_settings,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            client = MagicMock()
            client.chat.completions.create.return_value = _mock_completion(
                '{"title": "A"}', cost=0.0001
            )
            mock_openai_cls.return_value = client

            call_openrouter(
                "openai/gpt-4o-mini",
                "hi",
                json_mode=True,
                include_usage_cost=True,
            )
            call_kwargs = client.chat.completions.create.call_args.kwargs
            assert call_kwargs["response_format"] == {"type": "json_object"}
            assert call_kwargs["extra_body"] == {"usage": {"include": True}}

    def test_merges_extra_body_and_bounds_the_request(self):
        with (
            patch("shared.llms.openrouter.settings") as mock_settings,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            client = MagicMock()
            client.chat.completions.create.return_value = _mock_completion("{}")
            mock_openai_cls.return_value = client

            call_openrouter(
                "openai/gpt-oss-20b",
                "hi",
                include_usage_cost=True,
                extra_body={"reasoning": {"effort": "low"}},
                request_timeout=5.0,
            )
            call_kwargs = client.chat.completions.create.call_args.kwargs
            assert call_kwargs["extra_body"] == {
                "reasoning": {"effort": "low"},
                "usage": {"include": True},
            }
            assert call_kwargs["timeout"] == 5.0

    def test_api_exception_caught_into_error_field(self):
        with (
            patch("shared.llms.openrouter.settings") as mock_settings,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            client = MagicMock()
            client.chat.completions.create.side_effect = RuntimeError("rate limit")
            mock_openai_cls.return_value = client

            result = call_openrouter("anthropic/claude-3.5-haiku", "hi")
            assert not result.ok
            assert result.error is not None
            assert "rate limit" in result.error
            # Latency is still measured even on failure.
            assert result.latency_ms >= 0

    def test_records_token_counts_and_cost(self):
        with (
            patch("shared.llms.openrouter.settings") as mock_settings,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            client = MagicMock()
            client.chat.completions.create.return_value = _mock_completion(
                '{"title": "Auth fix"}', cost=0.00023
            )
            mock_openai_cls.return_value = client

            result = call_openrouter(
                "anthropic/claude-3.5-haiku", "hi", include_usage_cost=True
            )
            assert result.ok
            assert result.input_tokens == 120
            assert result.output_tokens == 8
            assert result.cost_usd == 0.00023

    def test_missing_cost_field_resolves_to_none(self):
        with (
            patch("shared.llms.openrouter.settings") as mock_settings,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            client = MagicMock()
            client.chat.completions.create.return_value = _mock_completion(
                '{"title": "Auth fix"}'
            )
            mock_openai_cls.return_value = client

            result = call_openrouter("anthropic/claude-3.5-haiku", "hi")
            assert result.ok
            assert result.cost_usd is None


class TestStripMarkdownFence:
    # Some models wrap JSON output in ```json ... ``` even when asked for raw
    # JSON; callers unwrap before json.loads.
    def test_json_fence(self):
        assert _strip_markdown_fence('```json\n{"title": "A"}\n```') == '{"title": "A"}'

    def test_plain_fence(self):
        assert _strip_markdown_fence('```\n{"title": "A"}\n```') == '{"title": "A"}'

    def test_inline_fence(self):
        assert _strip_markdown_fence('```json {"title": "A"} ```') == '{"title": "A"}'

    def test_unfenced_text_is_only_stripped(self):
        assert _strip_markdown_fence('  {"title": "A"}\n') == '{"title": "A"}'
