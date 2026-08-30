"""Tests for ``vicoa.utils.find_npm_cli``.

Covers the Linux daemon-launch bug: the daemon runs without nvm's
shell-sourced PATH entry, so npm-global CLIs installed under nvm are
invisible to ``shutil.which``. The resolver must still find them via the
nvm ``default`` version's bin (see ``_nvm_default_node_bin``) and the
``NVM_BIN`` / ``NPM_CONFIG_PREFIX`` env vars.

Note the scope: the nvm probe follows the ``default`` alias (or the sole
installed version), NOT every version ever installed — a stale global in a
no-longer-selected version must not read as installed. The dedicated
resolution tests live in ``test_utils_find_npm_cli_nvm.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vicoa.utils import find_npm_cli


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Sandbox ``Path.home()`` and ``$HOME`` to ``tmp_path``."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


@pytest.fixture
def empty_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip env so ``shutil.which`` only sees what each test plants."""
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("NVM_BIN", raising=False)
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\necho stub\n")
    path.chmod(0o755)
    return path


def _set_nvm_default(home: Path, version: str) -> None:
    """Point nvm's ``default`` alias at ``version`` (e.g. ``v20.11.1``)."""
    alias = home / ".nvm/alias"
    alias.mkdir(parents=True, exist_ok=True)
    (alias / "default").write_text(version + "\n")


class TestNvmGlob:
    """The bug class: CLI installed by npm-under-nvm, daemon PATH minimal."""

    def test_finds_claude_under_nvm_version_dir(
        self, fake_home: Path, empty_path: None
    ) -> None:
        target = _make_executable(fake_home / ".nvm/versions/node/v22.5.0/bin/claude")
        _set_nvm_default(fake_home, "v22.5.0")
        assert find_npm_cli("claude") == str(target)

    def test_finds_codex_acp_under_nvm(self, fake_home: Path, empty_path: None) -> None:
        target = _make_executable(
            fake_home / ".nvm/versions/node/v20.11.1/bin/codex-acp"
        )
        _set_nvm_default(fake_home, "v20.11.1")
        assert find_npm_cli("codex-acp") == str(target)

    def test_multiple_node_versions_probes_only_the_default(
        self, fake_home: Path, empty_path: None
    ) -> None:
        # User has 3 node versions installed, with the CLI in the one their
        # `default` alias selects. Only that version is probed — a stale copy
        # in a non-default version must not be preferred (or the CLI they
        # dropped in the default would go missing behind it).
        (fake_home / ".nvm/versions/node/v18.20.0/bin").mkdir(parents=True)
        target = _make_executable(
            fake_home / ".nvm/versions/node/v20.11.1/bin/opencode"
        )
        _make_executable(fake_home / ".nvm/versions/node/v22.5.0/bin/opencode")  # stale
        _set_nvm_default(fake_home, "v20.11.1")
        assert find_npm_cli("opencode") == str(target)

    def test_returns_none_when_nothing_installed(
        self, fake_home: Path, empty_path: None
    ) -> None:
        assert find_npm_cli("claude") is None


class TestEnvOverrides:
    def test_nvm_bin_env_takes_precedence_over_glob(
        self, fake_home: Path, empty_path: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # User's active nvm version sets NVM_BIN; if both that and a stale
        # globbed version contain the binary, NVM_BIN wins (it's what
        # `claude` would resolve to in their shell).
        active = _make_executable(fake_home / ".nvm/versions/node/v22.5.0/bin/claude")
        _make_executable(fake_home / ".nvm/versions/node/v18.0.0/bin/claude")
        monkeypatch.setenv("NVM_BIN", str(active.parent))
        assert find_npm_cli("claude") == str(active)

    def test_npm_config_prefix_env(
        self, fake_home: Path, empty_path: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prefix = fake_home / "custom-npm-prefix"
        target = _make_executable(prefix / "bin/codex-acp")
        monkeypatch.setenv("NPM_CONFIG_PREFIX", str(prefix))
        assert find_npm_cli("codex-acp") == str(target)


class TestExtraLocations:
    def test_claude_native_installer_path_via_extras(
        self, fake_home: Path, empty_path: None
    ) -> None:
        # Mirrors `find_claude_cli`'s use: Claude Code's native installer
        # drops the binary at ~/.claude/local/claude, which isn't in any
        # standard npm-global / system bin dir.
        target = _make_executable(fake_home / ".claude/local/claude")
        result = find_npm_cli(
            "claude", extra_locations=[fake_home / ".claude/local/claude"]
        )
        assert result == str(target)


class TestStandardLocations:
    def test_npm_global_bin(self, fake_home: Path, empty_path: None) -> None:
        target = _make_executable(fake_home / ".npm-global/bin/claude")
        assert find_npm_cli("claude") == str(target)

    def test_local_bin(self, fake_home: Path, empty_path: None) -> None:
        target = _make_executable(fake_home / ".local/bin/codex-acp")
        assert find_npm_cli("codex-acp") == str(target)

    def test_yarn_bin(self, fake_home: Path, empty_path: None) -> None:
        target = _make_executable(fake_home / ".yarn/bin/opencode")
        assert find_npm_cli("opencode") == str(target)

    def test_volta(self, fake_home: Path, empty_path: None) -> None:
        target = _make_executable(fake_home / ".volta/bin/claude")
        assert find_npm_cli("claude") == str(target)


class TestPathFirst:
    def test_shutil_which_takes_precedence(
        self, fake_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # A binary on PATH should beat any fallback, since PATH is what
        # the user's interactive shell resolves and is the closest match
        # to "what would `claude` mean here?".
        on_path_dir = tmp_path / "real-path"
        on_path_target = _make_executable(on_path_dir / "claude")
        _make_executable(fake_home / ".npm-global/bin/claude")  # decoy

        monkeypatch.setenv("PATH", str(on_path_dir))
        assert find_npm_cli("claude") == str(on_path_target)


class TestWindows:
    """Windows install locations.

    The daemon's PATH usually predates the install (Windows PATH changes only
    apply to *new* sessions), and Claude Code / npm / winget each drop the
    binary in a different, non-PATH directory. So ``shutil.which`` alone misses
    a perfectly-runnable ``claude`` — the resolver must probe the Windows dirs
    directly and honor Windows executable suffixes (``.exe`` / ``.cmd`` / ...).
    """

    @pytest.fixture
    def windows_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Force the Windows branch and clear its env so tests are hermetic.

        We flip the module's ``_is_windows()`` flag rather than ``os.name``
        itself: mutating ``os.name`` makes ``pathlib`` dispatch to
        ``WindowsPath``, which can't be instantiated on a POSIX host. Keeping
        ``os.name`` as-is leaves ``Path`` POSIX (so tmp files resolve) while
        still exercising every Windows candidate dir and suffix probe.
        """
        monkeypatch.setattr("vicoa.utils._is_windows", lambda: True)
        for var in ("LOCALAPPDATA", "APPDATA", "ProgramFiles", "USERPROFILE"):
            monkeypatch.delenv(var, raising=False)

    def _plant(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stub")
        return path

    def test_native_installer_local_bin_exe(
        self, fake_home: Path, empty_path: None, windows_mode: None
    ) -> None:
        # `irm claude.ai/install.ps1` -> %USERPROFILE%\.local\bin\claude.exe.
        # ~/.local/bin is already a candidate dir, but the file carries a .exe
        # suffix that the extensionless probe used to skip.
        target = self._plant(fake_home / ".local/bin/claude.exe")
        assert find_npm_cli("claude") == str(target)

    def test_winget_links_exe(
        self,
        fake_home: Path,
        empty_path: None,
        windows_mode: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        local_appdata = fake_home / "AppData/Local"
        monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
        target = self._plant(local_appdata / "Microsoft/WinGet/Links/claude.exe")
        assert find_npm_cli("claude") == str(target)

    def test_npm_global_appdata_cmd(
        self,
        fake_home: Path,
        empty_path: None,
        windows_mode: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        appdata = fake_home / "AppData/Roaming"
        monkeypatch.setenv("APPDATA", str(appdata))
        target = self._plant(appdata / "npm/claude.cmd")
        assert find_npm_cli("claude") == str(target)

    def test_claude_native_extra_location_exe(
        self, fake_home: Path, empty_path: None, windows_mode: None
    ) -> None:
        # find_claude_cli passes ~/.claude/local/claude as an extra location;
        # on Windows the real file is claude.exe.
        target = self._plant(fake_home / ".claude/local/claude.exe")
        result = find_npm_cli(
            "claude", extra_locations=[fake_home / ".claude/local/claude"]
        )
        assert result == str(target)

    def test_bare_extensionless_still_found(
        self, fake_home: Path, empty_path: None, windows_mode: None
    ) -> None:
        # npm also drops an extensionless shell shim next to the .cmd; a bare
        # file must still resolve (the .exe probe is additive, not a filter).
        target = self._plant(fake_home / ".local/bin/claude")
        assert find_npm_cli("claude") == str(target)

    def test_not_installed_returns_none(
        self, fake_home: Path, empty_path: None, windows_mode: None
    ) -> None:
        assert find_npm_cli("claude") is None


class TestUnreadableNvmDir:
    def test_unreadable_nvm_dir_does_not_crash(
        self,
        fake_home: Path,
        empty_path: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # If ~/.nvm/versions/node exists but iterdir() raises (perm
        # error, broken FS), the resolver should swallow and keep going.
        nvm = fake_home / ".nvm/versions/node"
        nvm.mkdir(parents=True)
        _make_executable(fake_home / ".local/bin/claude")

        real_iterdir = Path.iterdir

        def boom(self: Path):
            if self == nvm:
                raise OSError("permission denied")
            return real_iterdir(self)

        monkeypatch.setattr(Path, "iterdir", boom)
        # Fallback chain still resolves via ~/.local/bin.
        assert find_npm_cli("claude") == str(fake_home / ".local/bin/claude")


def test_skips_directories_named_like_binary(fake_home: Path, empty_path: None) -> None:
    # A directory at one of the candidate paths must not be returned —
    # ``is_file()`` rejects it, and the next candidate should be tried.
    (fake_home / ".npm-global/bin/claude").mkdir(parents=True)
    target = _make_executable(fake_home / ".local/bin/claude")
    assert find_npm_cli("claude") == str(target)


def test_extra_locations_iterable_accepts_tuple_or_list(
    fake_home: Path, empty_path: None
) -> None:
    target = _make_executable(fake_home / "custom/spot/claude")
    assert find_npm_cli(
        "claude", extra_locations=(fake_home / "custom/spot/claude",)
    ) == str(target)


def test_returns_none_when_nothing_anywhere(fake_home: Path, empty_path: None) -> None:
    assert find_npm_cli("does-not-exist") is None


def test_resolve_codex_acp_binary_uses_shared_resolver(
    fake_home: Path, empty_path: None
) -> None:
    """Regression guard: ``resolve_codex_acp_binary`` must follow the
    shared search order — VICOA_CODEX_ACP_PATH override first, then the
    nvm/Volta/snap/etc. fallback chain. Catches the Debian-codex bug
    where the old hardcoded path list missed ``~/.nvm/.../bin/codex-acp``.
    """
    from vicoa.agents.codex_acp import resolve_codex_acp_binary

    target = _make_executable(fake_home / ".nvm/versions/node/v22.5.0/bin/codex-acp")
    _set_nvm_default(fake_home, "v22.5.0")
    # Ensure no env override leaks in.
    os.environ.pop("VICOA_CODEX_ACP_PATH", None)
    resolved = resolve_codex_acp_binary()
    assert resolved is not None
    assert str(resolved) == str(target)
