"""AskUserQuestion dispatch prefers Claude's own tool input over the TUI scrape.

The terminal scrape keeps one line of each question and only the label and
short description of each option, so option previews (drafts, mockups) never
reached the dashboard. The JSONL monitor now records the exact tool input and
the terminal path sends it whenever it is the question on screen.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

from integrations.cli_wrappers.claude_code.messaging.ask_question import (
    build_ask_question_metadata,
    prefer_tool_input,
)
from integrations.cli_wrappers.claude_code.monitoring.jsonl_monitor import (
    JSONLMonitor,
)


def _scraped_tab() -> Dict[str, Any]:
    # What QuestionDetector returns for a wrapped question: only the line
    # holding the "?" survives.
    return {
        "question": "changelog draft should we ship?",
        "options_map": {
            "1": "1. Short - Two bullets",
            "2": "2. Long - Every change",
            "3": "3. Type something.",
        },
        "nav_tabs": ["Changelog"],
        "multi_select": False,
    }


def _tool_input_block() -> Dict[str, Any]:
    return {
        "type": "tool_use",
        "id": "toolu_123",
        "name": "AskUserQuestion",
        "input": {
            "questions": [
                {
                    "question": "Which changelog draft should we ship?",
                    "header": "Changelog",
                    "multiSelect": False,
                    "options": [
                        {
                            "label": "Short",
                            "description": "Two bullets",
                            "preview": "## v1.9.13\n\n- Fixes\n- Previews",
                        },
                        {"label": "Long", "description": "Every change"},
                    ],
                }
            ]
        },
    }


def _make_monitor() -> tuple[JSONLMonitor, MagicMock]:
    processor = MagicMock()
    monitor = JSONLMonitor.__new__(JSONLMonitor)
    monitor.log = lambda _msg: None  # noqa: E731
    monitor.message_processor = processor
    monitor.vicoa_client = None
    monitor._last_session_config = {}
    return monitor, processor


def _exact_metadata() -> Dict[str, Any]:
    monitor, _ = _make_monitor()
    metadata = monitor._extract_ask_user_question_metadata(_tool_input_block())
    assert metadata is not None
    return metadata


def test_jsonl_monitor_records_tool_input_with_previews() -> None:
    monitor, processor = _make_monitor()

    monitor._process_assistant_entry({"message": {"content": [_tool_input_block()]}})

    # The terminal path still owns dispatch; the monitor only records it.
    processor.process_assistant_message.assert_not_called()
    recorded = monitor.last_ask_user_question
    assert recorded is not None
    assert recorded["tool_use_id"] == "toolu_123"
    short, long = recorded["questions"][0]["options"]
    assert short["preview"] == "## v1.9.13\n\n- Fixes\n- Previews"
    assert "preview" not in long


def test_tool_input_replaces_scrape_for_the_question_on_screen() -> None:
    scraped = build_ask_question_metadata([_scraped_tab()])

    merged = prefer_tool_input(scraped, _exact_metadata())

    assert merged["tool_use_id"] == "toolu_123"
    question = merged["questions"][0]
    assert question["question"] == "Which changelog draft should we ship?"
    assert [o["label"] for o in question["options"]] == ["Short", "Long"]
    assert question["options"][0]["preview"].startswith("## v1.9.13")


def test_labels_match_when_question_line_is_unusable() -> None:
    tab = _scraped_tab()
    tab["question"] = "Waiting for your input..."
    scraped = build_ask_question_metadata([tab])

    merged = prefer_tool_input(scraped, _exact_metadata())

    assert merged["tool_use_id"] == "toolu_123"


def test_stale_tool_input_from_an_earlier_question_is_ignored() -> None:
    tab = {
        "question": "Which database should the preview stack use?",
        "options_map": {"1": "1. Postgres - Shared", "2": "2. SQLite - Local"},
        "nav_tabs": ["Database"],
        "multi_select": False,
    }
    scraped = build_ask_question_metadata([tab])

    assert prefer_tool_input(scraped, _exact_metadata()) is scraped


def test_scrape_is_used_until_the_jsonl_entry_is_read() -> None:
    scraped = build_ask_question_metadata([_scraped_tab()])

    assert prefer_tool_input(scraped, None) is scraped
