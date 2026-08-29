from __future__ import annotations

from types import SimpleNamespace

from vicoa import agent_processes
from vicoa.agent_processes import _classify, _is_vicoa_executable


# Frozen npm install path from the bug report — the wrapper runs in-process,
# so the `vicoa` binary's own argv is the only signature available to `ps`.
_FROZEN_BIN = (
    "/usr/local/lib/node_modules/@vicoa/cli/node_modules/@vicoa/cli-linux-x64/bin/vicoa"
)


class TestIsVicoaExecutable:
    def test_frozen_binary_path(self):
        assert _is_vicoa_executable(_FROZEN_BIN) is True

    def test_bare_name(self):
        assert _is_vicoa_executable("vicoa") is True

    def test_windows_exe(self):
        assert _is_vicoa_executable("vicoa.exe") is True

    def test_python_interpreter_is_not_vicoa(self):
        assert _is_vicoa_executable("/home/u/venv/bin/python") is False
        assert _is_vicoa_executable("python3.12") is False

    def test_vicoa_named_venv_python_is_not_vicoa(self):
        # A venv directory containing "vicoa" must not be mistaken for the
        # frozen binary — argv[0] is still the interpreter.
        assert _is_vicoa_executable("/home/u/vicoa-backend/.venv/bin/python") is False


class TestClassifyFrozenTui:
    """Frozen npm builds: the only signature is `<vicoa-binary> <agent>`."""

    def test_frozen_claude_tui(self):
        cmd = f"{_FROZEN_BIN} claude --session-id abc123"
        assert _classify(cmd) == ("claude", "tui")

    def test_frozen_amp_tui(self):
        assert _classify(f"{_FROZEN_BIN} amp") == ("amp", "tui")

    def test_frozen_codex_tui(self):
        # Regression guard: codex already worked, must keep working.
        assert _classify(f"{_FROZEN_BIN} codex --foo bar") == ("codex", "tui")

    def test_frozen_opencode_tui(self):
        assert _classify(f"{_FROZEN_BIN} opencode") == ("opencode", "tui")


class TestClassifyBareFrozenTui:
    """A frozen `vicoa` started with no subcommand (default agent) keeps the
    plain `.../vicoa` argv — the wrapper runs in-process and pty.forks the
    real agent child, which carries no vicoa signature. The parent must still
    be classified or the TUI is invisible to `vicoa ls` (the Linux bug)."""

    def test_bare_frozen_vicoa_is_default_tui(self, monkeypatch, tmp_path):
        # No config → default agent is claude.
        monkeypatch.setenv("HOME", str(tmp_path))
        assert _classify(_FROZEN_BIN) == ("claude", "tui")

    def test_bare_frozen_vicoa_with_global_flags(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert _classify(f"{_FROZEN_BIN} --no-relay --name work") == ("claude", "tui")

    def test_bare_frozen_vicoa_honors_config_default_agent(self, monkeypatch, tmp_path):
        cfg_dir = tmp_path / ".vicoa"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text('{"default_agent": "codex"}')
        monkeypatch.setenv("HOME", str(tmp_path))
        assert _classify(_FROZEN_BIN) == ("codex", "tui")

    def test_bare_source_vicoa_not_classified(self, monkeypatch, tmp_path):
        # Source install: parent is the interpreter, the `python -m` child
        # carries the signature — parent must NOT be classified (no double
        # count). HOME is irrelevant here but set for isolation.
        monkeypatch.setenv("HOME", str(tmp_path))
        cmd = "/home/u/venv/bin/python /home/u/venv/bin/vicoa"
        assert _classify(cmd) == (None, None)


class TestWindowsEnumeration:
    """Regression for the Windows `vicoa ls` bug: the PowerShell row format
    must use a real tab between fields. `t expands to a tab ONLY inside a
    double-quoted PowerShell string; the old single-quoted form emitted a
    literal backtick-t and every row failed the Python tab-split."""

    def test_ps_script_uses_double_quoted_tab(self):
        assert '"{0}`t{1}`t{2}"' in agent_processes._WINDOWS_PS_SCRIPT
        assert "'{0}`t{1}`t{2}'" not in agent_processes._WINDOWS_PS_SCRIPT

    def test_windows_parser_reads_tab_rows(self, monkeypatch):
        ps_output = (
            f"4242\t332\t{_FROZEN_BIN} headless --agent claude --session-id s1\n"
            "5555\t10\tC:\\Windows\\explorer.exe\n"
        )
        monkeypatch.setattr(
            agent_processes.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(stdout=ps_output, returncode=0),
        )
        agents = agent_processes._list_running_agents_windows()
        assert [(a.agent, a.kind, a.pid) for a in agents] == [
            ("claude", "headless", 4242)
        ]


class TestClassifySourceInstall:
    """Source installs spawn a `python -m` child; only the child is
    classified so the session is counted exactly once."""

    def test_source_claude_parent_not_classified(self):
        # The `vicoa claude` launcher under a Python interpreter — its
        # `python -m integrations.cli_wrappers.claude_code` child carries
        # the real signature, so the parent must NOT be classified.
        cmd = "/home/u/venv/bin/python /home/u/venv/bin/vicoa claude --session-id x"
        assert _classify(cmd) == (None, None)

    def test_source_claude_child_module(self):
        cmd = (
            "/home/u/venv/bin/python -m integrations.cli_wrappers.claude_code "
            "claude --session-id x"
        )
        assert _classify(cmd) == ("claude", "tui")

    def test_source_amp_child_module(self):
        cmd = "/home/u/venv/bin/python -m integrations.cli_wrappers.amp.amp amp"
        assert _classify(cmd) == ("amp", "tui")

    def test_source_codex_parent_classified(self):
        # codex/opencode do NOT spawn a `python -m` child, so the parent
        # under the interpreter is the one and only process to classify.
        cmd = "/home/u/venv/bin/python /home/u/venv/bin/vicoa codex"
        assert _classify(cmd) == ("codex", "tui")


class TestClassifyHeadlessAndNonTui:
    def test_headless_claude_module(self):
        cmd = "python -m integrations.headless.claude_code --cwd /proj"
        assert _classify(cmd) == ("claude", "headless")

    def test_headless_codex_module(self):
        cmd = "python -m integrations.headless.codex_acp --project-path /proj"
        assert _classify(cmd) == ("codex", "headless")

    def test_vicoa_headless_flag_form(self):
        assert _classify(f"{_FROZEN_BIN} headless --agent claude") == (
            "claude",
            "headless",
        )

    def test_vicoa_ls_not_classified(self):
        assert _classify(f"{_FROZEN_BIN} ls") == (None, None)

    def test_vicoa_daemon_not_classified(self):
        assert _classify(f"{_FROZEN_BIN} daemon") == (None, None)

    def test_unrelated_process_not_classified(self):
        assert _classify("/usr/bin/node /opt/app/server.js") == (None, None)


def test_list_running_agents_posix_frozen_claude_single_entry(monkeypatch):
    """End-to-end: a frozen claude TUI is enumerated exactly once."""
    ps_output = (
        f"  4242     05:32 {_FROZEN_BIN} claude --session-id sess-1\n"
        f"  4243  1-02:00:00 {_FROZEN_BIN} codex\n"
        "  4244     00:10 /usr/bin/node /opt/claude/cli.js\n"
    )
    monkeypatch.setattr(
        agent_processes.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=ps_output, returncode=0),
    )
    agents = agent_processes._list_running_agents_posix()
    by_agent = sorted((a.agent, a.kind) for a in agents)
    assert by_agent == [("claude", "tui"), ("codex", "tui")]
    claude = next(a for a in agents if a.agent == "claude")
    assert claude.pid == 4242
    assert claude.session_id == "sess-1"
