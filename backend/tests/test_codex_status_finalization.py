from types import SimpleNamespace
from unittest.mock import Mock

from integrations.headless.acp_base import ACPWrapperBase


class _DummyACPWrapper(ACPWrapperBase):
    def create_session(self) -> None:
        raise NotImplementedError

    def handle_notification(self, method: str, params: dict) -> None:
        raise NotImplementedError

    def send_prompt(self, message: str) -> None:
        raise NotImplementedError


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
    # The row exists — a terminal status is only written for a registered id.
    wrapper._registered = True

    ACPWrapperBase._cleanup(wrapper, final_status="FAILED")

    wrapper.acp.stop.assert_called_once()
    wrapper.vicoa_client.update_agent_instance_status.assert_called_once_with(
        "instance-456", "FAILED"
    )
    wrapper.vicoa_client.end_session.assert_not_called()
    wrapper.vicoa_client.close.assert_called_once()
