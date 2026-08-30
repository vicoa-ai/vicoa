"""Unit tests for shared.llms.openrouter — single-key multi-provider gateway."""

from unittest.mock import MagicMock, patch

from shared.llms.openrouter import (
    MAX_AUTO_TITLE_CHARS,
    _parse_title_json,
    call_openrouter,
    generate_title_via_openrouter,
)


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


class TestParseTitleJson:
    def test_well_formed(self):
        assert _parse_title_json('{"title": "Auth bug fix"}') == "Auth bug fix"

    def test_caps_to_40_chars(self):
        result = _parse_title_json('{"title": "%s"}' % ("A" * 80))
        assert result is not None
        assert len(result) == MAX_AUTO_TITLE_CHARS

    def test_bad_json_returns_none(self):
        assert _parse_title_json("not json") is None

    def test_none_input_returns_none(self):
        assert _parse_title_json(None) is None

    def test_missing_title_field_returns_none(self):
        assert _parse_title_json('{"summary": "nope"}') is None

    def test_empty_title_returns_none(self):
        assert _parse_title_json('{"title": "   "}') is None

    def test_strips_markdown_json_fence(self):
        # Anthropic Haiku 4.5+ wraps JSON output in ```json ... ``` even when
        # asked for raw JSON. Parser must unwrap before json.loads.
        assert _parse_title_json('```json\n{"title": "Auth fix"}\n```') == "Auth fix"

    def test_strips_plain_markdown_fence(self):
        assert _parse_title_json('```\n{"title": "Auth fix"}\n```') == "Auth fix"

    def test_strips_inline_fence(self):
        # Some models emit the fence on a single line with spaces.
        assert _parse_title_json('```json {"title": "Auth fix"} ```') == "Auth fix"


class TestGenerateTitleViaOpenRouter:
    def test_returns_parsed_title_on_success(self):
        with (
            patch("shared.llms.openrouter.settings") as mock_settings,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            client = MagicMock()
            client.chat.completions.create.return_value = _mock_completion(
                '{"title": "Safari logout bug"}', cost=0.0001
            )
            mock_openai_cls.return_value = client

            result = generate_title_via_openrouter(
                "Fix the Safari auto-logout bug",
                model="anthropic/claude-3.5-haiku",
            )

            assert result.parsed
            assert result.title == "Safari logout bug"
            assert result.input_tokens == 120
            assert result.cost_usd == 0.0001

    def test_propagates_api_error(self):
        with (
            patch("shared.llms.openrouter.settings") as mock_settings,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            client = MagicMock()
            client.chat.completions.create.side_effect = RuntimeError(
                "404 model not found"
            )
            mock_openai_cls.return_value = client

            result = generate_title_via_openrouter(
                "anything", model="nonexistent/model"
            )

            assert not result.parsed
            assert result.title is None
            assert result.error is not None
            assert "404" in result.error
