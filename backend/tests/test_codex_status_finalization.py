from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from integrations.headless.acp_base import ACPWrapperBase
from vicoa.agents import codex


class _DummyACPWrapper(ACPWrapperBase):
    def create_session(self) -> None:
        raise NotImplementedError

    def handle_notification(self, method: str, params: dict) -> None:
        raise NotImplementedError

    def send_prompt(self, message: str) -> None:
        raise NotImplementedError


def test_run_codex_marks_completed_session(monkeypatch):
    client = Mock()
    thread = Mock()
    client.register_agent_instance.return_value = SimpleNamespace(
        agent_instance_id="instance-123"
    )

    monkeypatch.setattr(codex, "_resolve_codex_binary", lambda: Path("/tmp/codex"))
    monkeypatch.setattr(codex, "VicoaClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(codex, "get_project_path", lambda cwd=None: "/tmp/project")
    monkeypatch.setattr(
        codex.subprocess,
        "Popen",
        lambda *args, **kwargs: SimpleNamespace(
            wait=lambda **kw: 0,
            poll=lambda: 0,
        ),
    )
    monkeypatch.setattr(
        codex.threading,
        "Thread",
        lambda *args, **kwargs: thread,
    )

    args = SimpleNamespace(
        base_url="https://api.vicoa.ai",
        agent_instance_id="instance-123",
        cwd="/tmp/project",
        name="Codex",
    )

    exit_code = codex.run_codex(args, ["--help"], "test-api-key")

    assert exit_code == 0
    client.end_session.assert_called_once_with("instance-123")
    client.update_agent_instance_status.assert_not_called()
    thread.start.assert_called_once()
    thread.join.assert_called_once_with(timeout=2.0)


def test_acp_cleanup_marks_failed_sessions_without_ending():
    wrapper = object.__new__(_DummyACPWrapper)
    wrapper.running = True
    wrapper.acp = Mock()
    wrapper.vicoa_client = Mock()
    wrapper.config = SimpleNamespace(
        agent_instance_id="instance-456", agent_type="Codex"
    )
    wrapper.debug_log_file = None
    wrapper.log = lambda message: None
    # ACPWrapperBase._cleanup now tears down the /ws subscriber too — set
    # the attrs ``__init__`` would have, so this object.__new__-based
    # fixture doesn't ``AttributeError`` before reaching the assertions.
    wrapper._ws_client = None
    wrapper._ws_thread = None

    ACPWrapperBase._cleanup(wrapper, final_status="FAILED")

    wrapper.acp.stop.assert_called_once()
    wrapper.vicoa_client.update_agent_instance_status.assert_called_once_with(
        "instance-456", "FAILED"
    )
    wrapper.vicoa_client.end_session.assert_not_called()
    wrapper.vicoa_client.close.assert_called_once()
