"""``extension_ui_request`` classification and response shaping.

The permission cases use the real frame from
``fixtures/omp/04-approval.jsonl`` — a multi-line free-text ``title`` with
``options: ["Approve", "Deny"]``.
"""

from __future__ import annotations

import pytest

from integrations.headless.pi_family import ui_requests


APPROVAL_FRAME = {
    "type": "extension_ui_request",
    "id": "1573388eac8cf7e2",
    "method": "select",
    "title": "Allow tool: write\nPath: approved.txt\nContent:\nok",
    "options": ["Approve", "Deny"],
}


def test_an_approve_deny_select_is_a_permission_prompt_not_a_question():
    assert ui_requests.classify(APPROVAL_FRAME) == "permission"


def test_a_select_with_real_choices_is_a_question():
    frame = {
        "method": "select",
        "title": "Which branch?",
        "options": ["main", "develop", "release"],
    }
    assert ui_requests.classify(frame) == "question"


@pytest.mark.parametrize(
    "method", ["setWidget", "setStatus", "setTitle", "set_editor_text"]
)
def test_presentation_methods_are_ignored_silently(method):
    """These fire in plain ``--mode rpc`` (setWidget at session start and end)
    and expect no response; replying to one would be a protocol error, and
    awaiting a human on it would hang the turn."""
    assert ui_requests.classify({"method": method, "id": "x"}) == "ignore"


def test_notify_and_open_url_are_notices():
    assert ui_requests.classify({"method": "notify", "message": "hi"}) == "notice"
    assert ui_requests.classify({"method": "open_url", "url": "https://x"}) == "notice"


def test_cancel_is_its_own_kind():
    assert ui_requests.classify({"method": "cancel", "targetId": "a"}) == "cancel"


def test_the_permission_prompt_carries_the_options_block_the_dashboard_parses():
    body = ui_requests.render_permission_prompt(APPROVAL_FRAME)
    assert "Allow tool: write" in body
    assert "[OPTIONS]\n1. Approve\n2. Deny\n[/OPTIONS]" in body


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("Approve", "Approve"),
        ("approve", "Approve"),
        ("  deny ", "Deny"),
        ("2", "Deny"),
        ("1", "Approve"),
        ("Approve this one", "Approve"),
        ("maybe", None),
        ("", None),
    ],
)
def test_option_matching_accepts_a_label_or_an_index(reply, expected):
    assert ui_requests.match_option(reply, ["Approve", "Deny"]) == expected


def test_confirm_becomes_a_yes_no_question_and_answers_with_confirmed():
    frame = {"id": "c1", "method": "confirm", "title": "Proceed?", "message": "Sure?"}
    questions, is_text = ui_requests.build_question(frame)
    assert not is_text
    assert [o["label"] for o in questions[0]["options"]] == ["Yes", "No"]
    response = ui_requests.answer_to_response(
        frame,
        {"cancelled": False, "answers": [{"mode": "option", "option_index": 0}]},
        is_text_mode=False,
    )
    assert response == {"id": "c1", "confirmed": True}


def test_input_becomes_a_free_text_question_and_answers_with_value():
    frame = {
        "id": "i1",
        "method": "input",
        "title": "Name?",
        "placeholder": "e.g. main",
    }
    questions, is_text = ui_requests.build_question(frame)
    assert is_text
    assert questions[0]["options"] == []
    assert "e.g. main" in questions[0]["question"]
    response = ui_requests.answer_to_response(
        frame,
        {"cancelled": False, "answers": [{"mode": "text", "text": " feature-x "}]},
        is_text_mode=True,
    )
    assert response == {"id": "i1", "value": "feature-x"}


def test_select_answers_with_the_chosen_label():
    frame = {
        "id": "s1",
        "method": "select",
        "title": "Which branch?",
        "options": ["main", "develop"],
        "optionDetails": [{"description": "stable"}, {"description": "next"}],
    }
    questions, _ = ui_requests.build_question(frame)
    assert questions[0]["options"][0] == {"label": "main", "description": "stable"}
    response = ui_requests.answer_to_response(
        frame,
        {"cancelled": False, "answers": [{"mode": "option", "option_index": 1}]},
        is_text_mode=False,
    )
    assert response == {"id": "s1", "value": "develop"}


def test_a_cancelled_answer_replies_cancelled_so_the_agent_stops_waiting():
    response = ui_requests.answer_to_response(
        APPROVAL_FRAME, {"cancelled": True}, is_text_mode=False
    )
    assert response == {"id": APPROVAL_FRAME["id"], "cancelled": True}


def test_an_unmatched_answer_cancels_rather_than_guessing():
    response = ui_requests.answer_to_response(
        APPROVAL_FRAME,
        {"cancelled": False, "answers": [{"mode": "option", "option_index": 99}]},
        is_text_mode=False,
    )
    assert response["cancelled"] is True


def test_empty_text_cancels_instead_of_sending_a_blank_value():
    frame = {"id": "i1", "method": "input", "title": "Name?"}
    response = ui_requests.answer_to_response(
        frame,
        {"cancelled": False, "answers": [{"mode": "text", "text": "   "}]},
        is_text_mode=True,
    )
    assert response["cancelled"] is True


def test_open_url_prefers_the_short_loopback_launch_url():
    text = ui_requests.render_notice(
        {
            "method": "open_url",
            "url": "https://provider/auth?code=very-long",
            "launchUrl": "http://127.0.0.1:9000/go",
            "instructions": "Sign in, then come back.",
        }
    )
    assert "http://127.0.0.1:9000/go" in text
    assert "Sign in, then come back." in text


def test_notify_renders_by_level():
    assert ui_requests.render_notice(
        {"method": "notify", "message": "careful", "notifyType": "warning"}
    ).startswith("⚠️")
    assert ui_requests.render_notice({"method": "notify", "message": ""}) is None
