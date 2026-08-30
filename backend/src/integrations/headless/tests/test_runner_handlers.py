"""Layer 2 tests for the runner's tool/permission/control handlers.

These tests construct a ``HeadlessClaudeRunner`` with ``FakeAsyncVicoaClient``
injected and exercise the callback methods the SDK invokes via
``can_use_tool``. They do **not** spawn the real Claude CLI and do **not**
drive ``ClaudeSDKClient`` — see ``README.md`` for the layering rationale.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Dict, List, Optional

import pytest
from claude_agent_sdk import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from integrations.headless.claude_code import InboundUserMessage

from _fakes import FakeAsyncVicoaClient


def _ctx() -> ToolPermissionContext:
    """Real SDK context — the handlers ignore most fields, so defaults are fine."""
    return ToolPermissionContext(tool_use_id="tu_test")


async def _noop_sleep(_seconds: float) -> None:
    """Stand-in for ``asyncio.sleep`` in tests.

    Cannot delegate to the real ``asyncio.sleep`` because the runner imports
    ``asyncio`` as a module-level name — patching that attribute mutates the
    shared module object, so any call back into ``asyncio.sleep`` would recurse.
    """
    return None


# ---------------------------------------------------------------------------
# _handle_permission_prompt — the generic permission flow.
# ---------------------------------------------------------------------------


async def test_permission_allow_once(make_runner, monkeypatch):
    """`Allow once` allows the tool with input unchanged and does not cache."""
    fake = FakeAsyncVicoaClient(permission_reply="Allow once")
    runner = make_runner(vicoa_client=fake)

    # Patch the 1s anti-race sleep inside _handle_permission_prompt to zero.
    monkeypatch.setattr("integrations.headless.claude_code.asyncio.sleep", _noop_sleep)

    tool_input: Dict[str, Any] = {"command": "ls -la"}
    result = await runner._handle_tool_use("Bash", tool_input, _ctx())
    await fake.drain_pending_deliveries()

    assert isinstance(result, PermissionResultAllow)
    assert result.updated_input == tool_input
    assert runner._permission_state == {}  # not cached on "Allow once"
    # One prompt was sent.
    assert len(fake.sent_messages) == 1
    sent = fake.sent_messages[0]
    # Semantic flag stays True so push/email/SMS still fire …
    assert sent["requires_user_input"] is True
    # … but polling is explicitly disabled — this is what closes §2c and §2g.
    assert sent["poll_for_reply"] is False
    assert "[OPTIONS]" in sent["content"]
    # Display labels are capitalized (the user-facing change).
    assert "Allow once" in sent["content"]
    assert "Always allow" in sent["content"]
    assert "Deny" in sent["content"]


async def test_permission_allow_always_is_cached(make_runner, monkeypatch):
    """`Always allow` caches the permission for the session.

    For Bash the cache key is the command prefix, so a different prefix
    re-prompts. For other tools the cache key is the tool name.
    """

    def handler(call: Dict[str, Any]) -> str:
        # First call (git status) → cache. Later call for a different
        # prefix gets "Allow once" so we can verify no second cache entry.
        return "Always allow" if "git" in call["content"] else "Allow once"

    fake = FakeAsyncVicoaClient(permission_reply=handler)
    runner = make_runner(vicoa_client=fake)
    monkeypatch.setattr("integrations.headless.claude_code.asyncio.sleep", _noop_sleep)

    first = await runner._handle_tool_use("Bash", {"command": "git status"}, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(first, PermissionResultAllow)
    assert runner._permission_state == {"Bash": {"git": True}}
    assert len(fake.sent_messages) == 1

    # Second call with the same prefix: short-circuits without re-prompting.
    second = await runner._handle_tool_use("Bash", {"command": "git log"}, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(second, PermissionResultAllow)
    assert len(fake.sent_messages) == 1, "should not re-prompt when cached"

    # Different prefix → fresh prompt (allowed once, not cached).
    third = await runner._handle_tool_use("Bash", {"command": "ls"}, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(third, PermissionResultAllow)
    assert len(fake.sent_messages) == 2
    assert "ls" not in runner._permission_state.get("Bash", {})


async def test_permission_reply_matching_is_case_insensitive(make_runner, monkeypatch):
    """Mobile keyboards sometimes auto-capitalize — accept "ALLOW ONCE" etc."""
    fake = FakeAsyncVicoaClient(permission_reply="ALLOW ONCE")
    runner = make_runner(vicoa_client=fake)
    monkeypatch.setattr("integrations.headless.claude_code.asyncio.sleep", _noop_sleep)

    result = await runner._handle_tool_use("Edit", {"file_path": "/x"}, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultAllow)


async def test_permission_deny(make_runner, monkeypatch):
    fake = FakeAsyncVicoaClient(permission_reply="Deny")
    runner = make_runner(vicoa_client=fake)
    monkeypatch.setattr("integrations.headless.claude_code.asyncio.sleep", _noop_sleep)

    result = await runner._handle_tool_use("Edit", {"file_path": "/x"}, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultDeny)
    assert "Permission denied by user" == result.message


async def test_permission_unrecognized_reply_denies_with_text(make_runner, monkeypatch):
    fake = FakeAsyncVicoaClient(permission_reply="maybe later")
    runner = make_runner(vicoa_client=fake)
    monkeypatch.setattr("integrations.headless.claude_code.asyncio.sleep", _noop_sleep)

    result = await runner._handle_tool_use("Edit", {"file_path": "/x"}, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultDeny)
    assert "maybe later" in result.message


async def test_permission_unexpected_exception_denies(make_runner, monkeypatch):
    def raise_runtime(call: Dict[str, Any]) -> BaseException:
        return RuntimeError("backend exploded")

    fake = FakeAsyncVicoaClient(send_message_handler=raise_runtime)
    runner = make_runner(vicoa_client=fake)
    monkeypatch.setattr("integrations.headless.claude_code.asyncio.sleep", _noop_sleep)

    result = await runner._handle_tool_use("Edit", {"file_path": "/x"}, _ctx())
    assert isinstance(result, PermissionResultDeny)
    assert "backend exploded" in result.message


async def test_permission_runner_without_client_denies(make_runner):
    runner = make_runner(vicoa_client=None)
    result = await runner._handle_tool_use("Edit", {"file_path": "/x"}, _ctx())
    assert isinstance(result, PermissionResultDeny)
    assert result.message == "Vicoa client not initialized"


async def test_permission_sse_routing_consumes_reply_from_queue(
    make_runner, monkeypatch
):
    """Direct repro of session 269d5bf3's bug: a permission reply must NOT
    leak onto ``_user_message_queue`` (it would surface as bogus user input
    on the next turn — "That message looks like a permission-prompt response
    that didn't get routed to a tool call…").

    With the registry pattern, the SSE listener calls
    ``_maybe_route_permission_reply`` BEFORE enqueueing, and the reply is
    consumed there.
    """
    fake = FakeAsyncVicoaClient(permission_reply="Allow once")
    runner = make_runner(vicoa_client=fake)
    monkeypatch.setattr("integrations.headless.claude_code.asyncio.sleep", _noop_sleep)

    result = await runner._handle_tool_use("Edit", {"file_path": "/x"}, _ctx())
    await fake.drain_pending_deliveries()

    assert isinstance(result, PermissionResultAllow)
    # The smoking gun: the reply did not leak onto the queue.
    assert runner._user_message_queue.empty()


async def test_plain_permission_reply_with_no_pending_future_is_dropped(make_runner):
    runner = make_runner()
    # No permission future pending.
    await runner._route("Allow once", (), message_id="p-1")
    assert runner._user_message_queue.empty()


async def test_ask_user_question_post_uses_requires_user_input(make_runner):
    """AUQ POST must use requires_user_input=True so push/email/SMS fire
    (per servers/shared/notification_utils.py:48-63), while
    poll_for_reply=False keeps the SDK out of the polling path."""
    fake = FakeAsyncVicoaClient(
        auq_reply=_build_submit_reply(
            [{"mode": "option", "option_index": 0, "question_multi_select": False}]
        )
    )
    runner = make_runner(vicoa_client=fake)

    await runner._handle_tool_use(
        "AskUserQuestion",
        {"questions": [{"question": "Q", "options": [{"label": "a"}]}]},
        _ctx(),
    )
    await fake.drain_pending_deliveries()

    sent = fake.sent_messages[0]
    assert sent["requires_user_input"] is True
    assert sent["poll_for_reply"] is False


# ---------------------------------------------------------------------------
# _handle_ask_user_question — the AskUserQuestion built-in tool path.
#
# Wire contract with the web/Flutter dashboards (see
# vicoa-web/components/dashboard/ask-user-question-panel.tsx and
# vicoa-app/lib/pages/agent_chat/components/ask_user_question_panel.dart):
#   submit → "<human> {"type":"control","setting":"ask_user_question","value":"submit:<urlsafe-base64-of-json>"}"
#   cancel → "<human> {"type":"control","setting":"ask_user_question","value":"cancel"}"
# The base64 payload is the JSON {message_id, answers[], display_answers[]}.
# ---------------------------------------------------------------------------


def _build_submit_reply(
    answers: List[Dict[str, Any]],
    display_answers: Optional[List[Dict[str, str]]] = None,
    message_id: str = "msg-1",
    request_id: Optional[str] = None,
) -> str:
    """Mirror the web/Flutter encoder so tests speak the same wire format."""
    payload: Dict[str, Any] = {
        "message_id": message_id,
        "answers": answers,
        "display_answers": display_answers or [],
    }
    if request_id is not None:
        payload["request_id"] = request_id
    raw = json.dumps(payload).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    control = json.dumps(
        {
            "type": "control",
            "setting": "ask_user_question",
            "value": f"submit:{encoded}",
        }
    )
    return f"Submit AskUserQuestion answers. {control}"


_CANCEL_REPLY = "Cancel AskUserQuestion prompt. " + json.dumps(
    {"type": "control", "setting": "ask_user_question", "value": "cancel"}
)


def _persist_only_summary(question: str, label: str) -> str:
    """Mirror buildAskUserQuestionSummaryMessage on the web side."""
    payload = {"message_id": "msg-x", "answers": [], "display_answers": []}
    raw = json.dumps(payload).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    control = json.dumps(
        {
            "type": "control",
            "action": "persist_only",
            "kind": "ask_user_question_summary",
            "value": f"v1:{encoded}",
        }
    )
    return f"Q: {question}\nA: {label}\n{control}"


async def test_ask_user_question_emits_structured_metadata(make_runner):
    """Runner should push a snake_case ask_user_question metadata block."""
    fake = FakeAsyncVicoaClient(
        auq_reply=_build_submit_reply(
            [
                {
                    "mode": "option",
                    "option_index": 0,
                    "question_multi_select": False,
                    "option_count": 1,
                }
            ]
        )
    )
    runner = make_runner(vicoa_client=fake)

    tool_input = {
        "questions": [
            {
                "header": "color",
                "question": "Pick a color",
                "options": [{"label": "red", "description": "Bold"}],
                "multiSelect": False,  # Claude's camelCase — runner must translate
            }
        ]
    }
    await runner._handle_tool_use("AskUserQuestion", tool_input, _ctx())
    await fake.drain_pending_deliveries()

    assert len(fake.sent_messages) == 1
    sent = fake.sent_messages[0]
    # Semantic flag stays True so push/email/SMS notifications still fire
    # (servers/shared/notification_utils.py:48-63 — only requires_user_input
    # gates the user-preference defaults).
    assert sent["requires_user_input"] is True
    # Polling is explicitly disabled — eliminating the §2g cursor race.
    assert sent["poll_for_reply"] is False
    metadata = sent["message_metadata"]
    assert metadata is not None
    auq_meta = metadata["ask_user_question"]
    assert auq_meta["tool_use_id"] == "tu_test"
    assert auq_meta["questions"][0]["question"] == "Pick a color"
    assert auq_meta["questions"][0]["header"] == "color"
    # multiSelect → multi_select (the key the dashboard parser expects).
    assert auq_meta["questions"][0]["multi_select"] is False
    assert auq_meta["questions"][0]["options"] == [
        {"label": "red", "description": "Bold"}
    ]
    # A request_id is stamped into the metadata so the dashboard can echo
    # it back via the SSE control reply.
    assert isinstance(auq_meta["request_id"], str) and auq_meta["request_id"]
    # The body is the minimal label — the picker UI renders questions/options
    # from the metadata; a verbose body would render as duplicate text
    # above the picker (the 17:53 / 17:55 log bug from session
    # 9aa429b5-3acb-4d2b-a3a8-d13278963911).
    assert sent["content"] == "🔧 Using tool: AskUserQuestion"
    # The metadata still carries the long prompt for clients that want it.
    assert "Pick a color" in auq_meta["prompt"]


async def test_ask_user_question_resolves_via_request_id(make_runner):
    """When the dashboard echoes back the runner's request_id, the registry
    routes the reply to the matching future regardless of message_id.

    This is the primary route: the dashboard reads ``request_id`` out of the
    prompt's ``message_metadata.ask_user_question`` and includes it in the
    submit payload's base64-encoded JSON.
    """

    def reply_for_call(call: Dict[str, Any]) -> str:
        rid = call["message_metadata"]["ask_user_question"]["request_id"]
        return _build_submit_reply(
            [
                {
                    "mode": "option",
                    "option_index": 1,
                    "question_multi_select": False,
                    "option_count": 2,
                }
            ],
            request_id=rid,
        )

    fake = FakeAsyncVicoaClient(auq_reply=reply_for_call)
    runner = make_runner(vicoa_client=fake)

    tool_input = {
        "questions": [
            {
                "question": "Pick a color",
                "options": [
                    {"label": "red", "description": "Bold"},
                    {"label": "purple", "description": "Royal"},
                ],
            }
        ]
    }
    result = await runner._handle_tool_use("AskUserQuestion", tool_input, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultAllow)
    assert (result.updated_input or {})["answers"] == {"Pick a color": "purple"}


async def test_ask_user_question_persist_only_summary_does_not_resolve(make_runner):
    """A persist_only summary arriving on the SSE stream is silently dropped
    and does NOT resolve the pending AUQ future.

    Reproduces the 17:55:00 / 17:55:11 race seen in
    `~/.vicoa/claude_headless/9aa429b5-3acb-4d2b-a3a8-d13278963911.log` —
    the summary used to short-circuit decoding to free-text fallback (which
    then fed "Q: ... A: ..." back to Claude as if it were the answer).
    """
    submit = _build_submit_reply(
        [
            {
                "mode": "option",
                "option_index": 1,
                "question_multi_select": False,
                "option_count": 2,
            }
        ]
    )
    summary = _persist_only_summary("Pick a color", "purple")
    # Summary arrives FIRST — that's the bug condition.
    fake = FakeAsyncVicoaClient(auq_reply=[summary, submit])
    runner = make_runner(vicoa_client=fake)

    tool_input = {
        "questions": [
            {
                "question": "Pick a color",
                "options": [
                    {"label": "red", "description": "Bold"},
                    {"label": "purple", "description": "Royal"},
                ],
            }
        ]
    }
    result = await runner._handle_tool_use("AskUserQuestion", tool_input, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultAllow)
    # The submit's option_index=1 means "purple". Crucially, the answer is
    # NOT the summary's "Q:/A:" body.
    assert (result.updated_input or {})["answers"] == {"Pick a color": "purple"}


async def test_ask_user_question_single_select_option(make_runner):
    """Standard single-question option submit → answer is the picked label."""
    fake = FakeAsyncVicoaClient(
        auq_reply=_build_submit_reply(
            [
                {
                    "mode": "option",
                    "option_index": 1,
                    "question_multi_select": False,
                    "option_count": 2,
                }
            ]
        )
    )
    runner = make_runner(vicoa_client=fake)

    tool_input = {
        "questions": [
            {
                "question": "Pick a color",
                "options": [
                    {"label": "red", "description": "Bold"},
                    {"label": "purple", "description": "Royal"},
                ],
            }
        ]
    }
    result = await runner._handle_tool_use("AskUserQuestion", tool_input, _ctx())
    await fake.drain_pending_deliveries()

    assert isinstance(result, PermissionResultAllow)
    updated = result.updated_input or {}
    assert updated["answers"] == {"Pick a color": "purple"}
    assert updated["questions"] == tool_input["questions"]


async def test_ask_user_question_multi_question_distinct_answers(make_runner):
    """Each question gets its own answer string — no broadcast."""
    fake = FakeAsyncVicoaClient(
        auq_reply=_build_submit_reply(
            [
                {
                    "mode": "option",
                    "option_index": 0,
                    "question_multi_select": False,
                    "option_count": 1,
                },
                {
                    "mode": "option",
                    "option_index": 1,
                    "question_multi_select": False,
                    "option_count": 2,
                },
            ]
        )
    )
    runner = make_runner(vicoa_client=fake)

    tool_input = {
        "questions": [
            {
                "header": "color",
                "question": "Pick a color",
                "options": [{"label": "purple", "description": "Royal"}],
            },
            {
                "header": "size",
                "question": "Pick a size",
                "options": [
                    {"label": "S", "description": "Small"},
                    {"label": "L", "description": "Large"},
                ],
            },
        ]
    }
    result = await runner._handle_tool_use("AskUserQuestion", tool_input, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultAllow)
    assert (result.updated_input or {})["answers"] == {
        "Pick a color": "purple",
        "Pick a size": "L",
    }


async def test_ask_user_question_multi_select_joins_labels(make_runner):
    """Multi-select replies come back as a comma-joined label string."""
    fake = FakeAsyncVicoaClient(
        auq_reply=_build_submit_reply(
            [
                {
                    "mode": "option",
                    "option_indexes": [0, 2],
                    "question_multi_select": True,
                    "option_count": 3,
                }
            ]
        )
    )
    runner = make_runner(vicoa_client=fake)

    tool_input = {
        "questions": [
            {
                "question": "Pick toppings",
                "options": [
                    {"label": "cheese", "description": ""},
                    {"label": "mushroom", "description": ""},
                    {"label": "onion", "description": ""},
                ],
                "multi_select": True,
            }
        ]
    }
    result = await runner._handle_tool_use("AskUserQuestion", tool_input, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultAllow)
    assert (result.updated_input or {})["answers"] == {"Pick toppings": "cheese, onion"}


async def test_ask_user_question_recovered_via_rest_reconcile(make_runner):
    """A picker submit whose realtime broadcast was dropped is recovered by REST.

    Reproduces the reported "the answer only comes back after I send another
    message" bug: the websocket never delivers the submit (dropped by the
    fire-and-forget bridge, or the socket was down mid idle wait — common on a
    long multi-question picker), so it is NOT auto-delivered here. The submit
    instead sits in the persisted tail, and the reconcile backstop's REST
    recovery (``_recover_pending_reply_via_rest``) pulls it and resolves the
    Future with the *real* structured answers — not the free-text fallback's
    guess from whatever the user types next.
    """
    fake = FakeAsyncVicoaClient()  # no auq_reply → nothing delivered live
    runner = make_runner(vicoa_client=fake)

    tool_input = {
        "questions": [
            {
                "header": "color",
                "question": "Pick a color",
                "options": [
                    {"label": "red", "description": ""},
                    {"label": "blue", "description": ""},
                ],
            },
            {
                "header": "size",
                "question": "Pick a size",
                "options": [
                    {"label": "S", "description": ""},
                    {"label": "L", "description": ""},
                ],
            },
        ]
    }

    # Kick off the AUQ handler; it POSTs the prompt and parks on the Future.
    task = asyncio.create_task(
        runner._handle_tool_use("AskUserQuestion", tool_input, _ctx())
    )
    # Let the POST land and the Future register before we recover.
    for _ in range(3):
        await asyncio.sleep(0)
    assert runner._auq_registry.has_pending()

    # The submit was persisted but never pushed live. Stage it (plus its
    # display-only summary) as the REST pending tail the reconcile reads.
    submit = _build_submit_reply(
        [
            {
                "mode": "option",
                "option_index": 1,
                "question_multi_select": False,
                "option_count": 2,
            },
            {
                "mode": "option",
                "option_index": 0,
                "question_multi_select": False,
                "option_count": 2,
            },
        ],
        message_id="msg-1",
    )
    fake.pending_raw = [
        {
            "id": "u-summary",
            "sender_type": "user",
            "content": _persist_only_summary("Pick a color", "blue"),
            "requires_user_input": False,
            "message_metadata": None,
        },
        {
            "id": "u-submit",
            "sender_type": "user",
            "content": submit,
            "requires_user_input": False,
            "message_metadata": None,
        },
    ]

    await runner._recover_pending_reply_via_rest()

    result = await asyncio.wait_for(task, timeout=1.0)
    assert isinstance(result, PermissionResultAllow)
    assert (result.updated_input or {})["answers"] == {
        "Pick a color": "blue",
        "Pick a size": "S",
    }
    # Recovery is a plain request/response, not the WS refetch.
    assert fake.get_pending_raw_calls == 1
    # The display-only summary and the resolved submit are both dropped from the
    # user-message queue — no spurious extra turn.
    assert runner._user_message_queue.empty()


async def test_ask_user_question_text_mode(make_runner):
    """When the user picks "Type something" the answer is the free text."""
    fake = FakeAsyncVicoaClient(
        auq_reply=_build_submit_reply(
            [{"mode": "text", "text": "  some thoughts  ", "option_count": 2}]
        )
    )
    runner = make_runner(vicoa_client=fake)

    tool_input = {
        "questions": [
            {
                "question": "What did you think?",
                "options": [
                    {"label": "good", "description": ""},
                    {"label": "bad", "description": ""},
                ],
            }
        ]
    }
    result = await runner._handle_tool_use("AskUserQuestion", tool_input, _ctx())
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultAllow)
    assert (result.updated_input or {})["answers"] == {
        "What did you think?": "some thoughts"
    }


async def test_ask_user_question_cancel_denies(make_runner):
    fake = FakeAsyncVicoaClient(auq_reply=_CANCEL_REPLY)
    runner = make_runner(vicoa_client=fake)

    result = await runner._handle_tool_use(
        "AskUserQuestion",
        {"questions": [{"question": "x", "options": [{"label": "y"}]}]},
        _ctx(),
    )
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultDeny)
    assert "cancelled" in result.message.lower()


async def test_ask_user_question_with_empty_questions_passes_through(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    result = await runner._handle_tool_use("AskUserQuestion", {"questions": []}, _ctx())
    assert isinstance(result, PermissionResultAllow)
    # No Vicoa message sent — the empty case short-circuits.
    assert fake.sent_messages == []


async def test_ask_user_question_without_client_denies(make_runner):
    runner = make_runner(vicoa_client=None)
    result = await runner._handle_tool_use(
        "AskUserQuestion", {"questions": [{"question": "x"}]}, _ctx()
    )
    assert isinstance(result, PermissionResultDeny)


async def test_sse_listener_route_resolves_pending_future(make_runner):
    """``_maybe_route_ask_user_question_reply`` is the SSE listener's eager
    route for AUQ replies. It must resolve a matching pending future
    *without* enqueueing the message into the user-message queue (otherwise
    the reply waits until the next conversation turn boundary, by which
    point the ``can_use_tool`` callback has long since timed out).
    """
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    fut = runner._auq_registry.create("req-sse")
    reply = _build_submit_reply(
        [{"mode": "option", "option_index": 0, "question_multi_select": False}],
        request_id="req-sse",
    )
    handled = await runner._maybe_route_ask_user_question_reply(reply)
    assert handled is True
    assert fut.done()


async def test_sse_listener_route_ignores_non_auq_messages(make_runner):
    """Plain user messages and unrelated control commands fall through to the
    normal queue path."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    # Plain text.
    assert await runner._maybe_route_ask_user_question_reply("hello world") is False
    # Unrelated control command.
    assert (
        await runner._maybe_route_ask_user_question_reply(
            '{"type":"control","setting":"permission_mode","value":"plan"}'
        )
        is False
    )


async def test_sse_listener_route_persist_only_does_not_resolve(make_runner):
    """A persist_only summary on the SSE stream must not resolve the future —
    the user's actual control submit will arrive separately. This protects
    the §2g-style race where the summary lands first."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    fut = runner._auq_registry.create("req-1")
    summary = _persist_only_summary("Pick a color", "purple")
    handled = await runner._maybe_route_ask_user_question_reply(summary)
    assert handled is False
    assert not fut.done(), "persist_only summary must NOT resolve the AUQ future"


async def test_ask_user_question_uses_send_lock(make_runner):
    """The AUQ POST is held under ``_send_lock`` so concurrent ``send_to_vicoa``
    POSTs cannot interleave with it. This is the in-process belt-and-braces
    that complements the Future-based no-poll fix for §2g.
    """
    fake = FakeAsyncVicoaClient(
        auq_reply=_build_submit_reply(
            [{"mode": "option", "option_index": 0, "question_multi_select": False}]
        )
    )
    runner = make_runner(vicoa_client=fake)

    # Hold the lock ourselves and verify the AUQ POST blocks waiting for it,
    # then unblocks after release.
    import asyncio as _asyncio

    await runner._send_lock.acquire()
    task = _asyncio.create_task(
        runner._handle_tool_use(
            "AskUserQuestion",
            {"questions": [{"question": "Q", "options": [{"label": "a"}]}]},
            _ctx(),
        )
    )
    # Yield enough times that the task would have made progress if it
    # weren't blocked on the lock. No POST should have landed yet.
    for _ in range(5):
        await _asyncio.sleep(0)
    assert fake.sent_messages == [], (
        "AUQ POST must wait on _send_lock — otherwise it races with send_to_vicoa"
    )
    runner._send_lock.release()
    result = await task
    await fake.drain_pending_deliveries()
    assert isinstance(result, PermissionResultAllow)
    assert fake.sent_messages != []


# ---------------------------------------------------------------------------
# SSE-listener routing for ask_user_question control replies
#
# The dashboard's AUQ reply is *also* echoed onto the SSE user-message stream
# (the runner can't tell the broker not to). _handle_control_command must
# silently acknowledge it so the user doesn't get an "Unknown setting"
# feedback message. The real decoding happens inline in
# _handle_ask_user_question via send_message's queued_user_messages.
# ---------------------------------------------------------------------------


async def test_control_command_silently_acks_ask_user_question(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    handled = await runner._handle_control_command(_CANCEL_REPLY)
    assert handled is True
    # Crucially: no feedback message was sent. The SSE listener should not
    # spam "Unknown setting" when it echoes an AUQ reply.
    assert fake.sent_messages == []


async def test_control_command_silently_swallows_persist_only_summary(make_runner):
    """The AskUserQuestion answer summary (`action: persist_only`) must be
    silently consumed by the SSE-listener path. Otherwise the summary's
    "Q: ... A: ..." body becomes the next conversation turn's user input.
    Direct repro of the 17:55:05 second-turn bug in session
    9aa429b5-3acb-4d2b-a3a8-d13278963911.
    """
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    handled = await runner._handle_control_command(
        _persist_only_summary("Pick a color", "purple")
    )
    assert handled is True
    assert fake.sent_messages == []  # no "Unknown setting" feedback


async def test_filter_control_commands_drops_persist_only(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    filtered = await runner._filter_control_commands(
        [
            {"content": "real user message"},
            {"content": _persist_only_summary("Pick a color", "purple")},
            {"content": "another real message"},
        ]
    )
    # Only the plain user messages survive; the summary is silently dropped
    # rather than being forwarded to Claude as a fresh prompt.
    assert [m.content for m in filtered] == [
        "real user message",
        "another real message",
    ]
    assert fake.sent_messages == []


# ---------------------------------------------------------------------------
# _handle_control_command — non-tool path; covers the SSE-delivered control
# messages from the dashboard.
# ---------------------------------------------------------------------------


async def test_control_command_unknown_setting_sends_feedback(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    handled = await runner._handle_control_command(
        '{"type": "control", "setting": "unknown_xyz", "value": "v"}'
    )
    assert handled is True
    # A feedback message was pushed back to Vicoa.
    assert any("Unknown setting" in m["content"] for m in fake.sent_messages)


async def test_control_command_invalid_permission_mode_sends_feedback(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    handled = await runner._handle_control_command(
        '{"type": "control", "setting": "permission_mode", "value": "bogus"}'
    )
    assert handled is True
    assert any("Invalid permission mode" in m["content"] for m in fake.sent_messages)


async def test_non_control_message_is_passthrough(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    assert await runner._handle_control_command("hello world") is False
    assert fake.sent_messages == []


async def test_filter_control_commands_strips_only_controls(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    filtered = await runner._filter_control_commands(
        [
            {"content": "do the thing"},
            {
                "content": '{"type": "control", "setting": "permission_mode", "value": "bogus"}'
            },
            {"content": "and then this"},
        ]
    )
    # The control message was consumed (and produced a feedback message); the
    # plain user messages are returned unchanged.
    assert [m.content for m in filtered] == ["do the thing", "and then this"]
    assert any("Invalid permission mode" in m["content"] for m in fake.sent_messages)


# ---------------------------------------------------------------------------
# _build_query_input — image attachments become SDK content blocks.
# ---------------------------------------------------------------------------


async def test_build_query_input_plain_text_passthrough(make_runner):
    from integrations.headless.claude_code import InboundUserMessage

    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    result = await runner._build_query_input(InboundUserMessage("hello"))
    assert result == "hello"


async def test_build_query_input_with_attachments(make_runner):
    import base64

    from integrations.headless.claude_code import InboundUserMessage
    from vicoa.attachments import AttachmentRef

    fake = FakeAsyncVicoaClient()
    fake.attachments = {"att-1": (b"img-bytes", "image/png")}
    runner = make_runner(vicoa_client=fake)

    message = InboundUserMessage(
        "describe this",
        (
            AttachmentRef("att-1", "image/png", "a.png"),
            AttachmentRef("att-2", "image/jpeg", "missing.jpg"),
        ),
    )
    result = await runner._build_query_input(message)
    items = [item async for item in result]
    assert len(items) == 1
    assert items[0]["type"] == "user"
    blocks = items[0]["message"]["content"]
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[0]["source"]["data"] == base64.b64encode(b"img-bytes").decode()
    # Failed download degrades to a note inside the text block.
    text_block = blocks[-1]
    assert text_block["type"] == "text"
    assert "describe this" in text_block["text"]
    assert "missing.jpg" in text_block["text"]


async def test_build_query_input_all_downloads_failed_falls_back_to_text(make_runner):
    from integrations.headless.claude_code import InboundUserMessage
    from vicoa.attachments import AttachmentRef

    runner = make_runner(vicoa_client=FakeAsyncVicoaClient())
    message = InboundUserMessage(
        "", (AttachmentRef("gone-1", "image/png", "gone.png"),)
    )
    result = await runner._build_query_input(message)
    assert isinstance(result, str)
    assert "gone.png" in result


# ---------------------------------------------------------------------------
# _route — threads the WS message id onto the queued InboundUserMessage.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_threads_message_id_onto_queue(make_runner):
    runner = make_runner()
    await runner._route("hello", (), message_id="m-1")
    msg = runner._user_message_queue.get_nowait()
    assert msg.content == "hello"
    assert msg.message_id == "m-1"


@pytest.mark.asyncio
async def test_route_free_text_answer_resolves_and_consumes(make_runner):
    """A typed chat answer to an open question resolves the AUQ future AND is
    marked consumed + remembered — so the turn-end ``already_queued`` remainder
    can't replay this plain row as a spurious fresh prompt."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    fut = runner._auq_registry.create("req-ft")

    await runner._route("use the second option", (), message_id="m-ft")

    assert fut.done()
    assert (await fut)["answers"] == [{"mode": "text", "text": "use the second option"}]
    assert runner._user_message_queue.empty()  # not queued as a prompt
    assert fake.mark_consumed_calls == ["m-ft"]  # consumed server-side
    assert "m-ft" in runner._seen_user_message_ids  # deduped vs already_queued


def test_should_reconcile_gates_on_idle_or_pending_reply(make_runner):
    """The reconcile backstop re-fetches only when a dropped message has nothing
    else to recover it: the runner is idle, or a reply Future is pending. During
    an active turn (neither) it stays quiet — a mid-turn drop is re-read at turn
    end via ``already_queued``."""
    runner = make_runner()

    # Active turn, nothing pending → quiet.
    runner._awaiting_input = False
    assert runner._should_reconcile() is False

    # Idle between turns → reconcile (recovers a stranded wake message).
    runner._awaiting_input = True
    assert runner._should_reconcile() is True

    # Mid-turn but an AUQ answer is outstanding → reconcile.
    runner._awaiting_input = False
    runner._auq_registry.create("req-x")
    assert runner._should_reconcile() is True
    runner._auq_registry.cancel("req-x")
    assert runner._should_reconcile() is False

    # Same for a pending permission prompt.
    runner._permission_registry.create("perm-x")
    assert runner._should_reconcile() is True


@pytest.mark.asyncio
async def test_route_typed_permission_word_answers_open_question(make_runner):
    """With a question open, a typed "Deny" is the user's answer to it — it must
    reach the free-text AUQ handler, not be dropped as an orphan permission
    reply (the step-3 guard only fires when NO question and NO prompt is open)."""
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    fut = runner._auq_registry.create("req-deny")

    await runner._route("Deny", (), message_id="m-deny")

    assert fut.done()
    assert (await fut)["answers"] == [{"mode": "text", "text": "Deny"}]
    assert runner._user_message_queue.empty()


# ---------------------------------------------------------------------------
# Cross-channel dedupe — WS queue vs REST ``already_queued`` remainder.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_dedupes_repeated_message_id(make_runner):
    runner = make_runner()
    await runner._route("hi", (), message_id="dup")
    await runner._route("hi", (), message_id="dup")  # WS re-delivery
    assert runner._user_message_queue.qsize() == 1


@pytest.mark.asyncio
async def test_already_queued_remainder_is_preserved(make_runner):
    runner = make_runner()
    # Simulate two mid-turn messages returned by mark_message_requires_input,
    # neither seen yet on the WS queue.
    queued = [
        {"id": "a", "content": "first", "message_metadata": None},
        {"id": "b", "content": "second", "message_metadata": None},
    ]
    await runner._enqueue_already_queued(queued)
    contents = [runner._user_message_queue.get_nowait().content for _ in range(2)]
    assert contents == ["first", "second"]  # nothing dropped


@pytest.mark.asyncio
async def test_already_queued_skips_ids_already_on_ws_queue(make_runner):
    runner = make_runner()
    await runner._route("hi", (), message_id="x")  # WS delivered it
    await runner._enqueue_already_queued(
        [{"id": "x", "content": "hi", "message_metadata": None}]
    )
    assert runner._user_message_queue.qsize() == 1  # not double-queued


# ---------------------------------------------------------------------------
# _wait_for_user_input / _on_ws_message_update — cancellation (Task B5).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_user_input_skips_cancelled(make_runner):
    runner = make_runner()
    await runner._route("stale", (), message_id="c-1")
    runner._cancelled_message_ids.add("c-1")
    # queue only holds the cancelled msg; wait should skip it and time out to None
    runner.running = True
    runner.interrupt_requested = True  # force the 5s loop to bail after skipping
    result = await runner._wait_for_user_input()
    assert result is None
    assert runner._user_message_queue.empty()


def test_on_ws_message_update_records_cancellation(make_runner):
    runner = make_runner()
    runner._on_ws_message_update(
        {"id": "c-2", "message_metadata": {"queue": {"status": "cancelled"}}}
    )
    assert "c-2" in runner._cancelled_message_ids


# ---------------------------------------------------------------------------
# run_conversation_turn — reports consumption at the top of the turn.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_conversation_turn_reports_consumption(make_runner):
    # `claude_client` is left unset (None) — the turn bails out right after
    # the mark-consumed call (before touching the Claude SDK), which keeps
    # this test focused on the new call without standing up a fake SDK
    # client. See README.md for the layering rationale.
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    result = await runner.run_conversation_turn(
        InboundUserMessage("hello", message_id="m-42")
    )

    assert fake.mark_consumed_calls == ["m-42"]
    assert result is None


@pytest.mark.asyncio
async def test_run_conversation_turn_skips_consumption_without_message_id(
    make_runner,
):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    await runner.run_conversation_turn(InboundUserMessage("hello"))

    assert fake.mark_consumed_calls == []


@pytest.mark.asyncio
async def test_run_conversation_turn_tolerates_mark_consumed_failure(make_runner):
    # Best-effort: a failed report must never block the turn itself.
    class _FailingClient(FakeAsyncVicoaClient):
        async def mark_message_consumed(self, message_id):
            raise RuntimeError("boom")

    fake = _FailingClient()
    runner = make_runner(vicoa_client=fake)

    result = await runner.run_conversation_turn(
        InboundUserMessage("hello", message_id="m-1")
    )

    assert result is None  # turn still proceeds to the no-claude_client bail-out


@pytest.mark.asyncio
async def test_run_conversation_turn_skips_cancelled_message(make_runner):
    """A message cancelled while it sat on the queue must be discarded before
    ``mark_message_consumed`` or any Claude turn runs — the skip at the top
    of ``run_conversation_turn`` (Task B5) falls straight through to
    ``_wait_for_user_input`` instead.
    """
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)
    runner._cancelled_message_ids.add("c-x")

    sentinel = InboundUserMessage("next turn", message_id="m-next")

    async def _fake_wait_for_user_input():
        return sentinel

    runner._wait_for_user_input = _fake_wait_for_user_input  # type: ignore[assignment]

    result = await runner.run_conversation_turn(
        InboundUserMessage("stale", (), message_id="c-x")
    )

    assert fake.mark_consumed_calls == []  # consumption never reported
    assert "c-x" not in runner._cancelled_message_ids  # id discarded
    assert result is sentinel  # fell through to _wait_for_user_input


# ---------------------------------------------------------------------------
# send_to_vicoa — message_metadata forwarding (Task C2). Task C3 uses this to
# tag sub-agent child messages with ``message_metadata.subagent``.
# ---------------------------------------------------------------------------


async def test_send_to_vicoa_forwards_message_metadata(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    metadata = {"subagent": {"name": "researcher", "id": "sub-1"}}
    await runner.send_to_vicoa("x", metadata)

    assert fake.sent_messages[-1]["message_metadata"] == metadata


async def test_send_to_vicoa_defaults_message_metadata_to_none(make_runner):
    fake = FakeAsyncVicoaClient()
    runner = make_runner(vicoa_client=fake)

    await runner.send_to_vicoa("x")

    assert fake.sent_messages[-1]["message_metadata"] is None
