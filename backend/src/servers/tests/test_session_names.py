"""Unit tests for shared.llms.session_names — session titles and worktree names.

One prompt names every session. A new worktree's spawn asks one OpenRouter
model (DeepSeek V4.1 Flash) for a title and a branch; every other session's
title falls through DeepSeek → Gemini Flash Lite → Anthropic. Neither raises:
a spawn keeps its random name, a session keeps a NULL title.
"""

from unittest.mock import MagicMock, patch

from shared.llms.openrouter import OpenRouterResult
from shared.llms.session_names import (
    _ANTHROPIC_MODEL,
    _NAMES_PROMPT,
    _OPENROUTER_EXTRA_BODY,
    _OPENROUTER_FALLBACK_MODEL,
    _OPENROUTER_MODEL,
    SessionNames,
    _call_anthropic_names,
    _call_openrouter_names,
    _naming_input,
    _parse_names_json,
    generate_conversation_title,
    generate_session_names,
    session_naming_configured,
)


def _ok(text: str) -> OpenRouterResult:
    return OpenRouterResult(
        text=text, input_tokens=1, output_tokens=1, cost_usd=None, latency_ms=1
    )


def _fork(history: str, request: str, source: str = "Add search bar") -> str:
    """A forked session's first message, shaped like the web/mobile fork."""
    return (
        "<chat-history>\n"
        "Chat history from an earlier Vicoa session, for context.\n"
        "Tool outputs are not included; re-read any file you need.\n"
        f"Source session: {source}\n"
        "Source directory: /home/nick/alpha\n\n"
        f"{history}\n"
        "</chat-history>\n\n"
        f"{request}"
    )


class TestParseNamesJson:
    def test_both_parts(self):
        assert _parse_names_json(
            '{"title": "修复拖拽排序", "branch": "fix-drag-sort"}'
        ) == SessionNames(title="修复拖拽排序", branch="fix-drag-sort")

    def test_language_field_is_ignored(self):
        assert _parse_names_json(
            '{"language": "Chinese", "title": "修复拖拽排序", "branch": "fix-drag-sort"}'
        ) == SessionNames(title="修复拖拽排序", branch="fix-drag-sort")

    def test_one_part_is_enough(self):
        assert _parse_names_json('{"branch": " fix-x "}') == SessionNames(
            title=None, branch="fix-x"
        )

    def test_long_title_returned_verbatim(self):
        # No server-side cap: cutting at 40 chars left titles ending mid-word.
        title = "Refactor auth middleware permission gate logic"
        assert _parse_names_json('{"title": "%s"}' % title) == SessionNames(
            title=title, branch=None
        )

    def test_markdown_fence(self):
        assert _parse_names_json('```json\n{"title": "A", "branch": "b"}\n```') == (
            SessionNames(title="A", branch="b")
        )

    def test_unusable(self):
        for raw in (None, "not json", "[]", '{"title": "", "branch": 3}'):
            assert _parse_names_json(raw) is None


class TestPrompt:
    def test_asks_for_the_language_before_the_title(self):
        # Without a named language the models wrote titles in languages the
        # message is not in.
        assert _NAMES_PROMPT.index('"language"') < _NAMES_PROMPT.index('"title"')
        assert "the user's own sentences" in _NAMES_PROMPT

    def test_sets_no_char_limit_on_the_title(self):
        # A "<= 40 chars" instruction made the model chase the boundary.
        assert "40" not in _NAMES_PROMPT


class TestNamingInput:
    def test_short_message_is_sent_whole(self):
        text = _naming_input("Fix the Safari logout bug")
        assert "<message>\nFix the Safari logout bug\n</message>" in text

    def test_long_message_keeps_its_start_and_end(self):
        # A long paste often ends with the user's own question about it.
        message = "Merchant listings issue\n" + "x" * 50_000 + "\n这些问题要怎么处理"
        text = _naming_input(message)
        assert "Merchant listings issue" in text
        assert "这些问题要怎么处理" in text
        assert len(text) < 2_100

    def test_fork_shows_the_new_message_apart_from_the_history(self):
        message = _fork(
            "User: Add a search bar to the Tasks page\nAgent: Done.",
            "看一下这里的修改合理吗",
        )
        text = _naming_input(message)
        assert "<message>\n看一下这里的修改合理吗\n</message>" in text
        assert 'Earlier session\'s title: "Add search bar".' in text
        assert "<history>" in text and "Agent: Done." in text
        assert "<chat-history>" not in text

    def test_fork_keeps_only_the_end_of_a_long_history(self):
        history = "User: first ask\n" + "Agent: step\n" * 500 + "User: latest ask"
        text = _naming_input(_fork(history, "继续"))
        assert "User: latest ask" in text
        assert "User: first ask" not in text
        assert len(text) < 2_100

    def test_fork_drops_edited_file_lists(self):
        history = "Agent: Updated both.\n  [edited: src/a.ts, src/b.ts]"
        text = _naming_input(_fork(history, "Ship it"))
        assert "[edited:" not in text
        assert "Agent: Updated both." in text

    def test_fork_of_a_fork_takes_what_follows_the_outer_history(self):
        inner = _fork("User: oldest", "middle ask", source="Inner")
        message = _fork(f"User: {inner}\nAgent: ok", "newest ask", source="Outer")
        text = _naming_input(message)
        assert "<message>\nnewest ask\n</message>" in text
        assert 'Earlier session\'s title: "Outer".' in text

    def test_fork_without_a_new_message_is_named_from_the_history(self):
        message = _fork("User: Fix the drag sort", "")
        text = _naming_input(message)
        assert "Fix the drag sort" in text
        assert "<history>" not in text


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

    def test_no_fallback_model_within_the_spawn_budget(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch(
                "shared.llms.session_names.call_openrouter",
                return_value=MagicMock(ok=False),
            ) as mock_call,
        ):
            mock_settings.openrouter_api_key = "sk-or"
            mock_settings.anthropic_api_key = "sk-ant"
            assert generate_session_names("Fix it") is None
            assert mock_call.call_count == 1

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
        assert "Fix it" in kwargs["prompt"]

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


class TestCallAnthropicNames:
    def _text_response(self, text: str) -> MagicMock:
        import anthropic

        block = MagicMock(spec=anthropic.types.TextBlock)
        block.text = text
        response = MagicMock()
        response.content = [block]
        return response

    def test_parses_a_fenced_answer_and_uses_haiku_45(self):
        # Haiku wraps JSON in ```json ... ``` even when asked for raw JSON.
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch("shared.llms.session_names.anthropic.Anthropic") as mock_cls,
        ):
            mock_settings.anthropic_api_key = "sk-ant"
            client = MagicMock()
            client.messages.create.return_value = self._text_response(
                '```json\n{"language": "English", "title": "Auth fix", "branch": "fix-auth"}\n```'
            )
            mock_cls.return_value = client
            assert _call_anthropic_names("Fix the auth bug") == SessionNames(
                title="Auth fix", branch="fix-auth"
            )
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["model"] == _ANTHROPIC_MODEL == "claude-haiku-4-5-20251001"

    def test_api_exception_is_none(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch("shared.llms.session_names.anthropic.Anthropic") as mock_cls,
        ):
            mock_settings.anthropic_api_key = "sk-ant"
            mock_cls.return_value.messages.create.side_effect = RuntimeError("429")
            assert _call_anthropic_names("anything") is None


class TestGenerateConversationTitle:
    """The background title: DeepSeek → Gemini Flash Lite → Anthropic."""

    def _keys(self, mock_settings: MagicMock, *, openrouter: bool, anthropic: bool):
        mock_settings.openrouter_api_key = "sk-or" if openrouter else ""
        mock_settings.anthropic_api_key = "sk-ant" if anthropic else ""

    def test_none_when_no_keys_configured(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch("shared.llms.session_names.call_openrouter") as mock_call,
        ):
            self._keys(mock_settings, openrouter=False, anthropic=False)
            assert generate_conversation_title("any message") is None
            mock_call.assert_not_called()

    def test_blank_message_is_not_sent(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch("shared.llms.session_names.call_openrouter") as mock_call,
        ):
            self._keys(mock_settings, openrouter=True, anthropic=True)
            assert generate_conversation_title("  \n ") is None
            mock_call.assert_not_called()

    def test_first_title_wins(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch(
                "shared.llms.session_names.call_openrouter",
                return_value=_ok('{"language": "English", "title": "Fix bug"}'),
            ) as mock_call,
        ):
            self._keys(mock_settings, openrouter=True, anthropic=True)
            assert generate_conversation_title("Fix the bug") == "Fix bug"
        assert [c.kwargs["model"] for c in mock_call.call_args_list] == [
            _OPENROUTER_MODEL
        ]

    def test_falls_through_to_gemini_then_anthropic(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch(
                "shared.llms.session_names.call_openrouter",
                return_value=MagicMock(ok=False),
            ) as mock_call,
            patch(
                "shared.llms.session_names._call_anthropic_names",
                return_value=SessionNames(title="Anthropic title", branch=None),
            ) as mock_anthropic,
        ):
            self._keys(mock_settings, openrouter=True, anthropic=True)
            assert generate_conversation_title("Fix bug") == "Anthropic title"
        assert [c.kwargs["model"] for c in mock_call.call_args_list] == [
            _OPENROUTER_MODEL,
            _OPENROUTER_FALLBACK_MODEL,
        ]
        mock_anthropic.assert_called_once_with("Fix bug")

    def test_an_answer_without_a_title_falls_through(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch(
                "shared.llms.session_names.call_openrouter",
                side_effect=[_ok('{"branch": "fix-bug"}'), _ok('{"title": "Gemini"}')],
            ),
        ):
            self._keys(mock_settings, openrouter=True, anthropic=False)
            assert generate_conversation_title("Fix bug") == "Gemini"

    def test_a_raising_provider_falls_through(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch(
                "shared.llms.session_names._call_openrouter_names",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "shared.llms.session_names._call_openrouter_fallback_names",
                return_value=SessionNames(title="Gemini", branch=None),
            ),
        ):
            self._keys(mock_settings, openrouter=True, anthropic=False)
            assert generate_conversation_title("Fix bug") == "Gemini"

    def test_anthropic_only_deployments(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch("shared.llms.session_names.call_openrouter") as mock_call,
            patch(
                "shared.llms.session_names._call_anthropic_names",
                return_value=SessionNames(title="Haiku", branch=None),
            ),
        ):
            self._keys(mock_settings, openrouter=False, anthropic=True)
            assert generate_conversation_title("Fix bug") == "Haiku"
            mock_call.assert_not_called()

    def test_none_when_every_provider_fails(self):
        with (
            patch("shared.llms.session_names.settings") as mock_settings,
            patch(
                "shared.llms.session_names.call_openrouter",
                return_value=MagicMock(ok=False),
            ),
            patch("shared.llms.session_names._call_anthropic_names", return_value=None),
        ):
            self._keys(mock_settings, openrouter=True, anthropic=True)
            assert generate_conversation_title("Fix bug") is None
