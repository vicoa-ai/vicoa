"""Unit tests for JSONLMonitor's session_config PATCH path.

The monitor watches the Claude jsonl. When it sees an assistant message with
a `model` we haven't reported yet, OR a top-level `permission-mode` event with
a new value, it PATCHes the agent_instances row's session_config so the mobile
chat header pill reflects the user's `/model` or `/permission` change.

Plan: plans/session-config-storage.md §3.3 (Post-init PATCH).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from integrations.cli_wrappers.claude_code.monitoring.jsonl_monitor import (
    JSONLMonitor,
)


INSTANCE_ID = "00000000-0000-0000-0000-000000000001"


class _FakeClient:
    """Captures patch_agent_instance calls without hitting the network."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def patch_agent_instance(
        self,
        agent_instance_id: str,
        *,
        name: Optional[str] = None,
        session_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.calls.append(
            {
                "agent_instance_id": agent_instance_id,
                "name": name,
                "session_config": session_config,
            }
        )
        return {}


def _make_monitor(client: _FakeClient) -> JSONLMonitor:
    """Build a JSONLMonitor bypassing __init__ — sets only attributes the
    session_config path reads. Mirrors the headless test pattern in
    src/integrations/headless/tests/conftest.py."""
    monitor = JSONLMonitor.__new__(JSONLMonitor)
    monitor.agent_instance_id = INSTANCE_ID
    monitor.log = lambda _msg: None  # noqa: E731
    monitor.message_processor = MagicMock()
    monitor.message_queue = None
    monitor.vicoa_client = client
    monitor._last_session_config = {}
    return monitor


def test_first_assistant_message_patches_model() -> None:
    client = _FakeClient()
    monitor = _make_monitor(client)
    entry = {
        "type": "assistant",
        "message": {"model": "claude-sonnet-4-6", "content": []},
    }
    monitor._process_entry(entry)
    assert client.calls == [
        {
            "agent_instance_id": INSTANCE_ID,
            "name": None,
            "session_config": {"model": "claude-sonnet-4-6"},
        }
    ]


def test_subsequent_same_model_does_not_patch() -> None:
    """Idempotency — we PATCH only on change, never on every assistant turn."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    entry = {
        "type": "assistant",
        "message": {"model": "claude-sonnet-4-6", "content": []},
    }
    monitor._process_entry(entry)
    monitor._process_entry(entry)
    monitor._process_entry(entry)
    assert len(client.calls) == 1


def test_model_switch_mid_session_patches_again() -> None:
    """User runs /model: next assistant message reports the new id, monitor
    PATCHes the row. This is the primary motivating use case."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor._process_entry(
        {"type": "assistant", "message": {"model": "claude-sonnet-4-6", "content": []}}
    )
    monitor._process_entry(
        {"type": "assistant", "message": {"model": "claude-opus-4-7", "content": []}}
    )
    assert [c["session_config"] for c in client.calls] == [
        {"model": "claude-sonnet-4-6"},
        {"model": "claude-opus-4-7"},
    ]


def test_permission_mode_event_patches() -> None:
    """The standalone {type:permission-mode, permissionMode:...} event fires
    at init AND on /permission changes. Both flow through the same patch."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor._process_entry({"type": "permission-mode", "permissionMode": "default"})
    assert client.calls == [
        {
            "agent_instance_id": INSTANCE_ID,
            "name": None,
            "session_config": {"permission_mode": "default"},
        }
    ]


def test_assistant_with_no_model_field_ignored() -> None:
    """A malformed or stripped assistant entry shouldn't blow up or PATCH."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor._process_entry({"type": "assistant", "message": {"content": []}})
    assert client.calls == []


def test_inline_permissionMode_on_user_entry_patches() -> None:
    """Claude doesn't always emit a standalone `permission-mode` event when
    the user presses Shift+Tab — instead the new mode is stamped on the next
    USER entry as a top-level `permissionMode` field. We must read that.

    Evidence: session 6837b5b8 — initial event was `bypassPermissions`, user
    pressed Shift+Tab, no fresh permission-mode event ever fired, but every
    USER entry after the cycle carried `permissionMode: 'auto'`.
    """
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor._process_entry(
        {
            "type": "user",
            "permissionMode": "auto",
            "message": {"content": "Hi"},
        }
    )
    assert client.calls == [
        {
            "agent_instance_id": INSTANCE_ID,
            "name": None,
            "session_config": {"permission_mode": "auto"},
        }
    ]


def test_inline_permissionMode_dedups_with_standalone_event() -> None:
    """The standalone event and inline field can BOTH fire for the same value
    on the same session — must not double-PATCH."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor._process_entry({"type": "permission-mode", "permissionMode": "auto"})
    monitor._process_entry(
        {
            "type": "user",
            "permissionMode": "auto",
            "message": {"content": "Hi"},
        }
    )
    assert len(client.calls) == 1


def test_inline_permissionMode_missing_is_ignored() -> None:
    """USER entries without `permissionMode` (older claude versions, or other
    user-content types) must not crash and must not PATCH."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor._process_entry({"type": "user", "message": {"content": "Hi"}})
    assert client.calls == []


def test_effort_command_patches_thinking_effort() -> None:
    """/effort in Claude TUI prints "Set effort level to <slug>: ..." in a
    local-command-stdout user entry. Parse the slug, PATCH session_config.

    Reference: session d2ceea17 cycled through high/medium/max/low/xhigh.
    """
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor._process_entry(
        {
            "type": "user",
            "message": {
                "content": (
                    "<local-command-stdout>Set effort level to high: "
                    "Comprehensive implementation with extensive testing"
                    "</local-command-stdout>"
                )
            },
        }
    )
    assert client.calls == [
        {
            "agent_instance_id": INSTANCE_ID,
            "name": None,
            "session_config": {"thinking_effort": "high"},
        }
    ]


def test_effort_command_max_session_only_still_patches() -> None:
    """The "(this session only)" suffix on max doesn't change the slug."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor._process_entry(
        {
            "type": "user",
            "message": {
                "content": (
                    "<local-command-stdout>Set effort level to max "
                    "(this session only): Maximum capability with deepest "
                    "reasoning</local-command-stdout>"
                )
            },
        }
    )
    assert client.calls[0]["session_config"] == {"thinking_effort": "max"}


def test_effort_command_idempotent_on_repeat() -> None:
    """Multiple /effort to the same slug → one PATCH (dedup cache)."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    entry = {
        "type": "user",
        "message": {
            "content": (
                "<local-command-stdout>Set effort level to medium: "
                "Balanced approach</local-command-stdout>"
            )
        },
    }
    monitor._process_entry(entry)
    monitor._process_entry(entry)
    assert len(client.calls) == 1


def test_effort_command_unknown_slug_ignored() -> None:
    """A typo or new Claude effort name we don't recognize must not PATCH a
    bogus value. Keep to known catalog ids."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor._process_entry(
        {
            "type": "user",
            "message": {
                "content": (
                    "<local-command-stdout>Set effort level to ludicrous: "
                    "Beyond reason</local-command-stdout>"
                )
            },
        }
    )
    assert client.calls == []


def test_effort_command_all_catalog_slugs_recognized() -> None:
    """Sweep the full catalog set so a future addition to PERMISSION_MODE_KEYWORDS
    or the catalog doesn't silently lose a valid slug."""
    for slug in ("low", "medium", "high", "xhigh", "max", "off"):
        client = _FakeClient()
        monitor = _make_monitor(client)
        monitor._process_entry(
            {
                "type": "user",
                "message": {
                    "content": (
                        f"<local-command-stdout>Set effort level to {slug}: "
                        f"some description</local-command-stdout>"
                    )
                },
            }
        )
        assert client.calls == [
            {
                "agent_instance_id": INSTANCE_ID,
                "name": None,
                "session_config": {"thinking_effort": slug},
            }
        ], f"slug={slug} not patched"


def test_patch_failure_does_not_raise() -> None:
    """Network blip on the PATCH shouldn't kill the JSONL monitor thread."""

    class _ExplodingClient:
        def patch_agent_instance(self, *_args, **_kwargs):
            raise RuntimeError("network down")

    monitor = _make_monitor(_ExplodingClient())  # type: ignore[arg-type]
    # Should not raise.
    monitor._process_entry(
        {"type": "assistant", "message": {"model": "claude-sonnet-4-6", "content": []}}
    )
    # And should not poison the cache — a successful retry on a different
    # value should still try (because the failed PATCH didn't update
    # _last_session_config).
    assert monitor._last_session_config == {}


def test_command_name_model_arg_patches_session_config() -> None:
    """User typed `/model claude-haiku-4-5` in the TUI — JSONL contains a
    `<command-name>/model</command-name><command-args>claude-haiku-4-5</command-args>`
    entry. Slug is right there, no need to reverse-map a label."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor.message_processor.suppress_cli_user_echo_until = 0.0
    monitor.message_queue = None
    entry = {
        "type": "user",
        "message": {
            "role": "user",
            "content": (
                "<command-name>/model</command-name>"
                "<command-args>claude-haiku-4-5</command-args>"
            ),
        },
    }
    monitor._process_entry(entry)
    assert client.calls == [
        {
            "agent_instance_id": INSTANCE_ID,
            "name": None,
            "session_config": {"model": "claude-haiku-4-5"},
        }
    ]


def test_command_name_effort_arg_patches_thinking_effort() -> None:
    """`/effort xhigh` in TUI — args block carries the slug directly. The
    stdout-confirmation regex path also fires, but this one wins because
    it doesn't need the prose to be in any particular shape."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor.message_processor.suppress_cli_user_echo_until = 0.0
    monitor.message_queue = None
    entry = {
        "type": "user",
        "message": {
            "role": "user",
            "content": (
                "<command-name>/effort</command-name><command-args>xhigh</command-args>"
            ),
        },
    }
    monitor._process_entry(entry)
    assert client.calls == [
        {
            "agent_instance_id": INSTANCE_ID,
            "name": None,
            "session_config": {"thinking_effort": "xhigh"},
        }
    ]


def test_command_name_empty_args_does_not_patch() -> None:
    """`/model` (no args) opens the picker; we don't know the destination
    until the user confirms. The stdout echo or next message.model
    self-heal will catch it."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor.message_processor.suppress_cli_user_echo_until = 0.0
    monitor.message_queue = None
    entry = {
        "type": "user",
        "message": {
            "role": "user",
            "content": (
                "<command-name>/model</command-name><command-args></command-args>"
            ),
        },
    }
    monitor._process_entry(entry)
    assert client.calls == []


def test_set_model_stdout_with_ansi_escapes_patches_slug() -> None:
    """The /model picker echoes `Set model to <ESC>[1mSonnet 4.6<ESC>[22m and
    saved as your default ...`. Args block stays empty in this flow, so this
    stdout line is the only path to recover the new slug."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor.message_processor.suppress_cli_user_echo_until = 0.0
    monitor.message_queue = None
    entry = {
        "type": "user",
        "message": {
            "role": "user",
            "content": (
                "<local-command-stdout>Set model to [1mSonnet 4.6"
                "[22m and saved as your default for new sessions"
                "</local-command-stdout>"
            ),
        },
    }
    monitor._process_entry(entry)
    assert any(
        c["session_config"] == {"model": "claude-sonnet-4-6"} for c in client.calls
    ), f"expected model PATCH, got {client.calls}"


def test_set_model_stdout_unknown_label_skips_patch() -> None:
    """If the label doesn't map to a catalog slug (e.g. the catalog hasn't
    caught up to a brand new model), we skip rather than guessing."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor.message_processor.suppress_cli_user_echo_until = 0.0
    monitor.message_queue = None
    entry = {
        "type": "user",
        "message": {
            "role": "user",
            "content": (
                "<local-command-stdout>Set model to Quasar 9000 and saved as "
                "your default for new sessions</local-command-stdout>"
            ),
        },
    }
    monitor._process_entry(entry)
    assert client.calls == []


def test_command_name_with_message_element_still_parses_args() -> None:
    """Real Claude jsonl entries put `<command-message>` between
    `<command-name>` and `<command-args>` — earlier regex without that
    allowance failed silently. Inline-args case (when present) must still
    PATCH from command-args."""
    client = _FakeClient()
    monitor = _make_monitor(client)
    monitor.message_processor.suppress_cli_user_echo_until = 0.0
    monitor.message_queue = None
    entry = {
        "type": "user",
        "message": {
            "role": "user",
            "content": (
                "<command-name>/model</command-name>\n"
                "            <command-message>model</command-message>\n"
                "            <command-args>claude-opus-4-7</command-args>"
            ),
        },
    }
    monitor._process_entry(entry)
    assert any(
        c["session_config"] == {"model": "claude-opus-4-7"} for c in client.calls
    ), f"expected model PATCH, got {client.calls}"
