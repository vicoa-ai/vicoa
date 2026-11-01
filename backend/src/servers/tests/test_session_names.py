"""Unit tests for shared.llms.session_names — title + branch from one call.

One OpenRouter model (DeepSeek V4.1 Flash) names the session; Anthropic is used
only when OpenRouter isn't configured. It returns None rather than raising, so
a spawn just keeps its random name.
"""

from unittest.mock import MagicMock, patch

from shared.llms.openrouter import OpenRouterResult
from shared.llms.session_names import (
    _NAMES_PROMPT,
    _OPENROUTER_EXTRA_BODY,
    _OPENROUTER_MODEL,
    SessionNames,
    _call_openrouter_names,
    _parse_names_json,
    generate_session_names,
    session_naming_configured,
)


def _ok(text: str) -> OpenRouterResult:
    return OpenRouterResult(
        text=text, input_tokens=1, output_tokens=1, cost_usd=None, latency_ms=1
    )


class TestParseNamesJson:
    def test_both_parts(self):
        assert _parse_names_json(
            '{"title": "修复拖拽排序", "branch": "fix-drag-sort"}'
        ) == SessionNames(title="修复拖拽排序", branch="fix-drag-sort")

    def test_one_part_is_enough(self):
        assert _parse_names_json('{"branch": " fix-x "}') == SessionNames(
            title=None, branch="fix-x"
        )

    def test_markdown_fence(self):
        assert _parse_names_json('```json\n{"title": "A", "branch": "b"}\n```') == (
            SessionNames(title="A", branch="b")
        )

    def test_unusable(self):
        for raw in (None, "not json", "[]", '{"title": "", "branch": 3}'):
            assert _parse_names_json(raw) is None


class TestGenerateSessionNames:
    def test_none_when_no_keys_configured(self):
        with patch("shared.llms.session_names.settings") as mock_settings:
            mock_settings.openrouter_api_key = ""
            mock_settings.anthropic_api_key = ""
            assert not session_naming_configured()
            assert generate_session_names("Fix the login bug") is None

    def test_blank_message_is_not_sent(self):
        with patch("shared.llms.session_names.call_openrouter") as mock_call:
            assert generate_session_names("   ") is None
            mock_call.assert_not_called()

    def test_asks_openrouter_when_configured(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch(
                "shared.llms.session_names._call_openrouter_names",
                return_value=SessionNames(title="T", branch="b"),
            ) as mock_openrouter,
            patch("shared.llms.session_names._call_anthropic_names") as mock_anthropic,
        ):
            mock_settings.openrouter_api_key = "sk-or"
            assert generate_session_names("Fix it") == SessionNames(
                title="T", branch="b"
            )
            mock_openrouter.assert_called_once_with("Fix it")
            mock_anthropic.assert_not_called()

    def test_anthropic_only_deployments_still_get_names(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch(
                "shared.llms.session_names._call_anthropic_names",
                return_value=SessionNames(title="T", branch="b"),
            ) as mock_anthropic,
        ):
            mock_settings.openrouter_api_key = ""
            mock_settings.anthropic_api_key = "sk-ant"
            assert generate_session_names("Fix it") == SessionNames(
                title="T", branch="b"
            )
            mock_anthropic.assert_called_once_with("Fix it")


class TestCallOpenRouterNames:
    def test_uses_deepseek_v41_flash_without_reasoning_and_a_bounded_timeout(self):
        with patch(
            "shared.llms.session_names.call_openrouter",
            return_value=_ok('{"title": "T", "branch": "b"}'),
        ) as mock_call:
            assert _call_openrouter_names("Fix it") == SessionNames(
                title="T", branch="b"
            )
        kwargs = mock_call.call_args.kwargs
        assert kwargs["model"] == _OPENROUTER_MODEL == "deepseek/deepseek-v4.1-flash"
        assert kwargs["extra_body"] == _OPENROUTER_EXTRA_BODY
        assert kwargs["json_mode"] is True
        assert kwargs["request_timeout"] <= 10

    def test_truncates_a_long_message(self):
        with patch(
            "shared.llms.session_names.call_openrouter", return_value=_ok("{}")
        ) as mock_call:
            _call_openrouter_names("x" * 50_000)
        prompt = mock_call.call_args.kwargs["prompt"]
        assert len(prompt) < len(_NAMES_PROMPT) + 2_100

    def test_error_result_is_none(self):
        failed = MagicMock(ok=False)
        with patch("shared.llms.session_names.call_openrouter", return_value=failed):
            assert _call_openrouter_names("Fix it") is None
