"""Standby (prewarm) launch of the ACP runners (opencode and the generic ACP agents).

``vicoa headless --standby`` starts the agent and does the ACP handshake
(``initialize``) while the user is still typing, and the session only becomes
visible once the daemon hands it the prompt (``vicoa.standby``). These tests
drive ``ACPWrapperBase._setup`` against a fake agent and a recording Vicoa
client and pin the contract:

* nothing is written to the session row before the go line: no registration,
  no PATCH, no message, no status, no heartbeat, no WS;
* the agent's own session (``session/new``) is created only after
  registration: agents keep their own session history, and an unused prewarm
  must leave nothing in it;
* a discard exits without registering;
* the adopted prompt runs as turn 1 locally, is POSTed for the chat in the
  background, and the server's echo of that row is dropped by id;
* agent messages wait for that POST, so no reply is filed above the prompt.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pytest

from integrations.headless import acp_base
from integrations.headless.acp_base import ACPWrapperBase, ACPWrapperConfig
from vicoa.standby import STANDBY_ENV

_INSTANCE_ID = "11111111-2222-3333-4444-555555555555"
_ACP_SESSION_ID = "acp-sess-1"
_PROMPT_ROW_ID = "msg-prompt"

#: Server calls that write to (or would create) the session row.
_INSTANCE_WRITES = {
    "register_agent_instance",
    "patch_agent_instance",
    "send_user_message",
    "send_message",
    "update_agent_instance_status",
    "end_session",
    "heartbeat",
    "ws",
}


class _Config(ACPWrapperConfig):
    def __init__(self) -> None:
        self.api_key = "test-key"
        self.base_url = "http://localhost:0"
        self.agent_instance_id = _INSTANCE_ID
        self.project_path = "/tmp/acp-standby-test"
        self.agent_type = "TestAgent"
        self.agent_command = "testagent"
        self.name = "TestAgent"
        self.is_resuming = False
        self.initial_prompt = None
        self.catalog_agent_id = "testagent"

    def get_acp_command(self) -> list[str]:
        return ["testagent", "acp"]

    def get_acp_env(self) -> dict[str, str]:
        return {}


class _Response:
    def __init__(self, result: Dict[str, Any]) -> None:
        self.result = result
        self.error = None
        self.is_error = False

    def raise_for_error(self) -> None:
        return None


class _FakeACP:
    """Answers the bring-up requests the way a real agent does."""

    def __init__(self, events: list[str], **_kwargs: Any) -> None:
        self.events = events
        self.stopped = False
        self.on_late_response: Optional[Callable[..., None]] = None

    def start(self) -> None:
        self.events.append("acp:start")

    def send_request(
        self, method: str, params: Dict[str, Any], timeout: Optional[float] = None
    ) -> _Response:
        del params, timeout
        self.events.append(f"acp:{method}")
        if method == "initialize":
            return _Response({"protocolVersion": 1, "agentCapabilities": {}})
        if method == "session/new":
            return _Response(
                {
                    "sessionId": _ACP_SESSION_ID,
                    "models": {
                        "availableModels": [{"modelId": "m-1", "name": "Model 1"}],
                        "currentModelId": "m-1",
                    },
                }
            )
        return _Response({})

    def stop(self) -> None:
        self.stopped = True
        self.events.append("acp:stop")


class _Registration:
    agent_instance_id = _INSTANCE_ID


class _MessageResponse:
    message_id = "msg-agent"


class _FakeVicoa:
    """Records every server call, in order, into the shared event list."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.patches: list[Dict[str, Any]] = []
        self.user_posts: list[Dict[str, Any]] = []
        self.agent_posts: list[str] = []
        # Set to hold the prompt's POST open (it "lands" when released).
        self.user_post_gate: Optional[threading.Event] = None
        self.session = object()

    def register_agent_instance(self, **_kwargs: Any) -> _Registration:
        self.events.append("register_agent_instance")
        return _Registration()

    def patch_agent_instance(self, instance_id: str, **kwargs: Any) -> Dict[str, Any]:
        del instance_id
        self.events.append("patch_agent_instance")
        self.patches.append(kwargs)
        return {}

    def send_user_message(self, **kwargs: Any) -> Dict[str, Any]:
        if self.user_post_gate is not None:
            self.user_post_gate.wait(5)
        self.events.append("send_user_message")
        self.user_posts.append(kwargs)
        return {"message_id": _PROMPT_ROW_ID}

    def send_message(self, *, content: str, **_kwargs: Any) -> _MessageResponse:
        self.events.append("send_message")
        self.agent_posts.append(content)
        return _MessageResponse()

    def update_agent_instance_status(self, instance_id: str, status: str) -> None:
        del instance_id
        self.events.append(f"update_agent_instance_status:{status}")

    def end_session(self, instance_id: str) -> None:
        del instance_id
        self.events.append("end_session")

    def sync_commands(self, **_kwargs: Any) -> None:
        self.events.append("sync_commands")

    def close(self) -> None:
        pass


class _FakeHeartbeat:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def start(self) -> None:
        self.events.append("heartbeat")

    def stop(self) -> None:
        pass


class _FakeWs:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        events.append("ws")

    def run(self) -> None:
        pass

    def wait_until_ready(self, timeout: float) -> bool:
        del timeout
        return True

    def stop(self) -> None:
        pass


class _Harness:
    def __init__(self, wrapper: ACPWrapperBase, events: list[str]) -> None:
        self.wrapper = wrapper
        self.events = events
        self.go: Optional[Dict[str, Any]] = {"prompt": "fix the build"}

    @property
    def vicoa(self) -> _FakeVicoa:
        client = self.wrapper.vicoa_client
        assert isinstance(client, _FakeVicoa)
        return client

    def settle(self) -> None:
        """Wait for the background PATCH and prompt POST threads."""
        for thread in (
            self.wrapper._config_patch_thread,
            self.wrapper._prompt_post_thread,
        ):
            if thread is not None:
                thread.join(5)

    def before_go(self) -> list[str]:
        return self.events[: self.events.index("go")]


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Harness:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv(STANDBY_ENV, "1")
    events: list[str] = []
    monkeypatch.setattr(acp_base, "VicoaClient", lambda **_kwargs: _FakeVicoa(events))
    monkeypatch.setattr(
        acp_base, "ACPClient", lambda **kwargs: _FakeACP(events, **kwargs)
    )
    monkeypatch.setattr(
        acp_base, "SessionHeartbeat", lambda **_kwargs: _FakeHeartbeat(events)
    )
    monkeypatch.setattr(
        acp_base, "SessionMessagesWsClient", lambda **_kwargs: _FakeWs(events)
    )
    wrapper = ACPWrapperBase(_Config())
    harness = _Harness(wrapper, events)

    def fake_read_go(timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        del timeout
        events.append("go")
        return harness.go

    monkeypatch.setattr(acp_base, "read_go", fake_read_go)
    return harness


def _echo(row_id: str, content: str = "fix the build") -> Dict[str, Any]:
    return {"id": row_id, "content": content, "sender_type": "USER"}


def test_the_agent_comes_up_before_anything_touches_the_session_row(
    harness: _Harness,
) -> None:
    harness.wrapper._setup()

    before = harness.before_go()
    assert before == ["acp:start", "acp:initialize"]
    assert not _INSTANCE_WRITES.intersection(before)
    assert harness.events.index("register_agent_instance") > harness.events.index("go")


def test_the_agents_own_session_is_created_only_after_registration(
    harness: _Harness,
) -> None:
    """``session/new`` is what puts an entry in the agent's own history."""
    harness.wrapper._setup()

    assert "acp:session/new" not in harness.before_go()
    assert harness.events.index("acp:session/new") > harness.events.index(
        "register_agent_instance"
    )


def test_a_discard_exits_without_registering(harness: _Harness) -> None:
    harness.go = None
    harness.wrapper._install_signal_handlers = lambda: None  # type: ignore[method-assign]

    assert harness.wrapper.run() == 0

    assert not _INSTANCE_WRITES.intersection(harness.events)
    assert "acp:stop" in harness.events
    assert not (Path.home() / ".vicoa" / "session_registered" / _INSTANCE_ID).exists()


def test_the_adopted_prompt_runs_as_turn_one_and_is_posted_for_the_chat(
    harness: _Harness,
) -> None:
    harness.wrapper._setup()
    harness.settle()

    assert harness.wrapper.message_queue == [("fix the build", (), None)]
    [post] = harness.vicoa.user_posts
    assert post["content"] == "fix the build"
    assert post["mark_as_read"] is False
    assert harness.wrapper._startup_complete is True


def test_the_prompt_shows_in_the_chat_before_the_agents_session_is_created(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """session/new runs after the go now, so the chat must not wait for it."""
    posted = threading.Event()
    real_post = harness.vicoa.send_user_message

    def post(**kwargs: Any) -> Dict[str, Any]:
        result = real_post(**kwargs)
        posted.set()
        return result

    real_request = _FakeACP.send_request

    def request(
        self: _FakeACP,
        method: str,
        params: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> _Response:
        if method == "session/new":
            posted.wait(2)  # a POST started only after this would come too late
        return real_request(self, method, params, timeout)

    harness.vicoa.send_user_message = post  # type: ignore[method-assign]
    monkeypatch.setattr(_FakeACP, "send_request", request)
    harness.wrapper._setup()

    assert harness.events.index("send_user_message") < harness.events.index(
        "acp:session/new"
    )


def test_the_session_writes_follow_registration_as_on_a_cold_start(
    harness: _Harness,
) -> None:
    harness.wrapper._setup()
    harness.settle()

    metadata = [
        p["instance_metadata"]
        for p in harness.vicoa.patches
        if p.get("instance_metadata")
    ]
    configs = [
        p["session_config"] for p in harness.vicoa.patches if p.get("session_config")
    ]
    assert metadata == [{"acp_session_id": _ACP_SESSION_ID}]
    assert configs and configs[-1]["current_model"] == "m-1"
    assert harness.events.index("patch_agent_instance") > harness.events.index(
        "register_agent_instance"
    )


def test_an_agent_that_may_create_its_session_early_does_so_before_the_go(
    harness: _Harness,
) -> None:
    """``standby_creates_session`` (Cursor): session/new during the prewarm,
    with nothing written to the session row until it registers."""
    harness.wrapper.config.standby_creates_session = True
    harness.wrapper._setup()
    harness.settle()

    before = harness.before_go()
    assert before == ["acp:start", "acp:initialize", "acp:session/new"]
    assert harness.events.count("acp:session/new") == 1
    metadata = [
        p["instance_metadata"]
        for p in harness.vicoa.patches
        if p.get("instance_metadata")
    ]
    configs = [
        p["session_config"] for p in harness.vicoa.patches if p.get("session_config")
    ]
    assert metadata == [{"acp_session_id": _ACP_SESSION_ID}]
    assert configs and configs[-1]["current_model"] == "m-1"
    assert harness.events.index("patch_agent_instance") > harness.events.index(
        "register_agent_instance"
    )


def test_a_change_while_an_early_session_waits_is_sent_after_registration(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.wrapper.config.standby_creates_session = True
    wrapper = harness.wrapper
    real_read_go = acp_base.read_go

    def read_go(timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        # A config_option_update arriving while the prewarm waits.
        wrapper.current_model_id = "m-2"
        wrapper._patch_session_config({"current_model": "m-2"})
        return real_read_go(timeout)

    monkeypatch.setattr(acp_base, "read_go", read_go)
    wrapper._setup()
    harness.settle()

    assert not _INSTANCE_WRITES.intersection(harness.before_go())
    configs = [
        p["session_config"] for p in harness.vicoa.patches if p.get("session_config")
    ]
    assert configs[-1]["current_model"] == "m-2"


def test_the_echo_of_the_adopted_prompt_is_dropped_by_id(harness: _Harness) -> None:
    harness.wrapper._setup()
    harness.settle()
    harness.wrapper.message_queue.clear()

    harness.wrapper._on_ws_user_message(_echo(_PROMPT_ROW_ID))  # live broadcast
    harness.wrapper._on_ws_user_message(_echo(_PROMPT_ROW_ID))  # catch-up replay
    assert harness.wrapper.message_queue == []

    # The user sending the same words again is a new row, and runs.
    harness.wrapper._on_ws_user_message(_echo("msg-again"))
    assert harness.wrapper.message_queue == [("fix the build", (), "msg-again")]


def test_an_echo_that_beats_the_post_response_waits_for_its_id(
    harness: _Harness,
) -> None:
    gate = threading.Event()
    harness.vicoa.user_post_gate = gate
    harness.wrapper._setup()
    harness.wrapper.message_queue.clear()

    delivered = threading.Thread(
        target=harness.wrapper._on_ws_user_message, args=(_echo(_PROMPT_ROW_ID),)
    )
    delivered.start()
    delivered.join(0.2)
    assert delivered.is_alive()  # waiting for the POST to say which row is ours

    gate.set()
    delivered.join(5)
    assert harness.wrapper.message_queue == []


def test_an_agent_reply_waits_for_the_prompt_post(harness: _Harness) -> None:
    gate = threading.Event()
    harness.vicoa.user_post_gate = gate
    harness.wrapper._setup()

    reply = threading.Thread(
        target=harness.wrapper._forward_agent_text, args=("on it",)
    )
    reply.start()
    reply.join(0.2)
    assert harness.vicoa.agent_posts == []

    gate.set()
    reply.join(5)
    assert harness.vicoa.agent_posts == ["on it"]
    assert harness.events.index("send_user_message") < harness.events.index(
        "send_message"
    )


def test_a_go_without_a_prompt_registers_and_waits_for_the_user(
    harness: _Harness,
) -> None:
    harness.go = {"prompt": None}
    harness.wrapper._setup()
    harness.settle()

    assert "register_agent_instance" in harness.events
    assert harness.vicoa.user_posts == []
    assert harness.wrapper.message_queue == []


def test_a_cold_start_still_registers_before_the_agent_starts(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(STANDBY_ENV)
    harness.wrapper._setup()

    assert "go" not in harness.events
    assert harness.events.index("register_agent_instance") < harness.events.index(
        "acp:start"
    )
