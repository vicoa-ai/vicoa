"""Unit tests for session-title generation in shared.llms.utils.

Covers the provider chain (OpenRouter DeepSeek v3.2 → OpenRouter
Gemini-flash-lite → Anthropic Haiku 4.5). The prompt and JSON title parser are
covered in test_openrouter.py.
"""

from unittest.mock import MagicMock, patch

from shared.llms.openrouter import TitleResult
from shared.llms.utils import (
    _call_anthropic_title,
    _call_openrouter_deepseek_title,
    _call_openrouter_gemini_title,
    _call_openrouter_title,
    generate_conversation_title,
)


class TestGenerateConversationTitleFallback:
    """Chain: OpenRouter DeepSeek v3.2 → OpenRouter Gemini-lite → Anthropic.

    `generate_conversation_title` must never raise. It returns the first
    successful provider's title, or None if every provider is unconfigured
    or fails — callers leave `instance.name` NULL so the UI keeps its
    fallback (latest_message on web).
    """

    def test_returns_none_when_no_keys_configured(self):
        with patch("shared.llms.utils.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""
            mock_settings.openrouter_api_key = ""
            assert generate_conversation_title("any message") is None

    def test_deepseek_success_short_circuits_fallbacks(self):
        with (
            patch(
                "shared.llms.utils._call_openrouter_deepseek_title",
                return_value="DeepSeek Title",
            ) as mock_deepseek,
            patch("shared.llms.utils._call_openrouter_gemini_title") as mock_gemini,
            patch("shared.llms.utils._call_anthropic_title") as mock_anthropic,
        ):
            assert generate_conversation_title("Fix bug") == "DeepSeek Title"
            mock_deepseek.assert_called_once_with("Fix bug")
            mock_gemini.assert_not_called()
            mock_anthropic.assert_not_called()

    def test_falls_through_to_gemini_when_deepseek_fails(self):
        with (
            patch(
                "shared.llms.utils._call_openrouter_deepseek_title",
                return_value=None,
            ) as mock_deepseek,
            patch(
                "shared.llms.utils._call_openrouter_gemini_title",
                return_value="Gemini Title",
            ) as mock_gemini,
            patch("shared.llms.utils._call_anthropic_title") as mock_anthropic,
        ):
            assert generate_conversation_title("Fix bug") == "Gemini Title"
            mock_deepseek.assert_called_once_with("Fix bug")
            mock_gemini.assert_called_once_with("Fix bug")
            mock_anthropic.assert_not_called()

    def test_falls_through_to_anthropic_when_openrouter_fails(self):
        with (
            patch(
                "shared.llms.utils._call_openrouter_deepseek_title",
                return_value=None,
            ),
            patch(
                "shared.llms.utils._call_openrouter_gemini_title",
                return_value=None,
            ),
            patch(
                "shared.llms.utils._call_anthropic_title",
                return_value="Anthropic Title",
            ) as mock_anthropic,
        ):
            assert generate_conversation_title("Fix bug") == "Anthropic Title"
            mock_anthropic.assert_called_once_with("Fix bug")

    def test_returns_none_when_all_three_providers_fail(self):
        with (
            patch(
                "shared.llms.utils._call_openrouter_deepseek_title",
                return_value=None,
            ),
            patch(
                "shared.llms.utils._call_openrouter_gemini_title",
                return_value=None,
            ),
            patch("shared.llms.utils._call_anthropic_title", return_value=None),
        ):
            assert generate_conversation_title("Fix bug") is None

    def test_provider_exception_falls_through_to_next(self):
        with (
            patch(
                "shared.llms.utils._call_openrouter_deepseek_title",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "shared.llms.utils._call_openrouter_gemini_title",
                return_value="Gemini Title",
            ),
            patch("shared.llms.utils._call_anthropic_title") as mock_anthropic,
        ):
            assert generate_conversation_title("Fix bug") == "Gemini Title"
            mock_anthropic.assert_not_called()


class TestAnthropicProvider:
    """`_call_anthropic_title` — key gating + Haiku 4.5 model + parsing."""

    def _text_response(self, text: str) -> MagicMock:
        import anthropic

        block = MagicMock(spec=anthropic.types.TextBlock)
        block.text = text
        response = MagicMock()
        response.content = [block]
        return response

    def test_no_key_returns_none(self):
        with patch("shared.llms.utils.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""
            assert _call_anthropic_title("anything") is None

    def test_parses_json_response_and_uses_haiku_45(self):
        with (
            patch("shared.llms.utils.settings") as mock_settings,
            patch("shared.llms.utils.anthropic.Anthropic") as mock_cls,
        ):
            mock_settings.anthropic_api_key = "sk-ant-xxx"
            client = MagicMock()
            client.messages.create.return_value = self._text_response(
                '{"title": "Auth bug fix"}'
            )
            mock_cls.return_value = client

            assert _call_anthropic_title("Fix the auth bug") == "Auth bug fix"
            # Verify the migrated model name (claude-3-5-haiku-latest is EOL).
            assert (
                client.messages.create.call_args.kwargs["model"]
                == "claude-haiku-4-5-20251001"
            )

    def test_handles_markdown_fenced_response(self):
        # Haiku 4.5 wraps JSON in ```json ... ``` — the parser must unwrap.
        with (
            patch("shared.llms.utils.settings") as mock_settings,
            patch("shared.llms.utils.anthropic.Anthropic") as mock_cls,
        ):
            mock_settings.anthropic_api_key = "sk-ant-xxx"
            client = MagicMock()
            client.messages.create.return_value = self._text_response(
                '```json\n{"title": "Refactor DB"}\n```'
            )
            mock_cls.return_value = client

            assert _call_anthropic_title("Refactor DB") == "Refactor DB"

    def test_api_exception_returns_none(self):
        with (
            patch("shared.llms.utils.settings") as mock_settings,
            patch("shared.llms.utils.anthropic.Anthropic") as mock_cls,
        ):
            mock_settings.anthropic_api_key = "sk-ant-xxx"
            client = MagicMock()
            client.messages.create.side_effect = RuntimeError("rate limit")
            mock_cls.return_value = client

            assert _call_anthropic_title("anything") is None


class TestOpenRouterFallback:
    """`_call_openrouter_title` and the two fixed-model wrappers."""

    def _ok_result(self, title: str) -> TitleResult:
        return TitleResult(
            title=title,
            raw_text=f'{{"title": "{title}"}}',
            input_tokens=80,
            output_tokens=12,
            cost_usd=0.00004,
            latency_ms=900,
            error=None,
        )

    def _error_result(self, error: str) -> TitleResult:
        return TitleResult(
            title=None,
            raw_text=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=None,
            latency_ms=200,
            error=error,
        )

    def test_no_openrouter_key_returns_none(self):
        with patch("shared.llms.utils.settings") as mock_settings:
            mock_settings.openrouter_api_key = ""
            assert _call_openrouter_title("hi", model="deepseek/deepseek-v3.2") is None

    def test_returns_title_on_success(self):
        with (
            patch("shared.llms.utils.settings") as mock_settings,
            patch(
                "shared.llms.utils.generate_title_via_openrouter",
                return_value=self._ok_result("OpenRouter Title"),
            ) as mock_call,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"

            result = _call_openrouter_title("Fix bug", model="deepseek/deepseek-v3.2")

            assert result == "OpenRouter Title"
            mock_call.assert_called_once()
            assert mock_call.call_args.kwargs["model"] == "deepseek/deepseek-v3.2"
            assert mock_call.call_args.kwargs["max_tokens"] == 60
            # Production doesn't need per-call cost reporting — bench-only.
            assert mock_call.call_args.kwargs["include_usage_cost"] is False

    def test_returns_none_on_error_result(self):
        with (
            patch("shared.llms.utils.settings") as mock_settings,
            patch(
                "shared.llms.utils.generate_title_via_openrouter",
                return_value=self._error_result("404 model not found"),
            ),
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            assert _call_openrouter_title("hi", model="deepseek/deepseek-v3.2") is None

    def test_swallows_unexpected_exception(self):
        with (
            patch("shared.llms.utils.settings") as mock_settings,
            patch(
                "shared.llms.utils.generate_title_via_openrouter",
                side_effect=RuntimeError("network broke"),
            ),
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            assert _call_openrouter_title("hi", model="deepseek/deepseek-v3.2") is None

    def test_deepseek_wrapper_passes_correct_model(self):
        with (
            patch("shared.llms.utils.settings") as mock_settings,
            patch(
                "shared.llms.utils.generate_title_via_openrouter",
                return_value=self._ok_result("X"),
            ) as mock_call,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            _call_openrouter_deepseek_title("hi")
            assert mock_call.call_args.kwargs["model"] == "deepseek/deepseek-v3.2"

    def test_gemini_wrapper_passes_correct_model(self):
        with (
            patch("shared.llms.utils.settings") as mock_settings,
            patch(
                "shared.llms.utils.generate_title_via_openrouter",
                return_value=self._ok_result("X"),
            ) as mock_call,
        ):
            mock_settings.openrouter_api_key = "sk-or-xxx"
            _call_openrouter_gemini_title("hi")
            assert mock_call.call_args.kwargs["model"] == "google/gemini-3.1-flash-lite"
