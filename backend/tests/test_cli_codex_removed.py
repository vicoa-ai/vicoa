"""`vicoa codex` no longer launches anything; it points at the app instead.

Codex still runs from the app (the daemon drives the user's own
`codex app-server`); only the terminal mode, which needed a bundled fork of
the Codex CLI, is gone. These pin what the command says and that it bails out
before any login, daemon start or sync.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

from vicoa import cli


def _forbid(name: str):
    def _fail(*_args, **_kwargs):
        raise AssertionError(f"{name} must not run for `vicoa codex`")

    return _fail


@pytest.fixture
def no_side_effects(monkeypatch):
    monkeypatch.setattr(cli, "ensure_api_key", _forbid("ensure_api_key"))
    monkeypatch.setattr(
        cli, "maybe_start_machine_daemon", _forbid("maybe_start_machine_daemon")
    )
    monkeypatch.setattr(cli, "check_for_updates", lambda: None)


def test_run_agent_default_prints_pointer_and_exits_1(no_side_effects, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.run_agent_default(types.SimpleNamespace(agent="codex"), [])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "`vicoa codex` is no longer supported." in err
    assert "vicoa session start --agent codex --dir" in err
    assert os.getcwd() in err
    # Only a default-agent launch gets the "change your default" hint.
    assert "--set-default" not in err


@pytest.mark.parametrize(
    "argv",
    [
        ["vicoa", "codex"],
        ["vicoa", "codex", "--resume", "some-session"],
        ["vicoa", "--agent", "codex"],
    ],
)
def test_explicit_codex_invocations(no_side_effects, monkeypatch, capsys, argv):
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(cli, "load_user_config", lambda: {})
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "`vicoa codex` is no longer supported." in err
    assert "--set-default" not in err


def test_bare_vicoa_with_codex_default_explains_how_to_change_it(
    no_side_effects, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["vicoa"])
    monkeypatch.setattr(cli, "load_user_config", lambda: {"default_agent": "codex"})
    monkeypatch.setattr(cli.platform, "system", lambda: "Darwin")
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "`vicoa codex` is no longer supported." in err
    assert "vicoa --set-default claude" in err
