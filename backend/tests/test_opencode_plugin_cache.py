"""`vicoa opencode`'s handling of OpenCode's cached copy of the Vicoa plugin.

OpenCode 1.18+ keeps each npm plugin in its own project under
``~/.cache/opencode/packages/<name>@<spec>/``; older releases used one shared
``~/.cache/opencode/node_modules/``. `--upgrade` must clear the copy OpenCode
actually loads, and the pre-install must land where OpenCode looks.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from vicoa.agents import opencode

PLUGIN = "@vicoa/opencode"


def _install_project(cache: Path, spec: str = "latest") -> Path:
    """A plugin project as OpenCode 1.18 leaves it."""
    project = cache / "packages" / f"{PLUGIN}@{spec}"
    package = project / "node_modules" / PLUGIN
    package.mkdir(parents=True)
    (package / "package.json").write_text('{"version": "0.2.0"}')
    (project / "package.json").write_text(
        '{"dependencies": {"@vicoa/opencode": "0.2.0"}}'
    )
    return project


def _install_legacy(cache: Path) -> Path:
    package = cache / "node_modules" / PLUGIN
    package.mkdir(parents=True)
    (package / "package.json").write_text('{"version": "0.1.5"}')
    return package


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "opencode"
    root.mkdir()
    monkeypatch.setattr(opencode, "OPENCODE_CACHE_DIR", root)
    # Never touch the real ~/.config/opencode from a test.
    monkeypatch.setattr(opencode, "_ensure_plugin_registered", lambda: True)
    return root


def test_upgrade_clears_the_current_layout(
    cache: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    latest = _install_project(cache)
    pinned = _install_project(cache, "0.1.9")
    other = cache / "packages" / "@vicoa" / "opencode-extra@latest"
    other.mkdir(parents=True)
    unrelated = cache / "packages" / "some-plugin@latest"
    unrelated.mkdir(parents=True)

    opencode.upgrade_plugin()

    assert not latest.exists()
    assert not pinned.exists()
    assert other.exists() and unrelated.exists()
    out = capsys.readouterr().out
    assert f"Removed cached plugin from {latest}" in out
    assert "nothing to clear" not in out


def test_upgrade_clears_the_old_layout_too(cache: Path) -> None:
    legacy = _install_legacy(cache)
    latest = _install_project(cache)

    opencode.upgrade_plugin()

    assert not legacy.exists()
    assert not latest.exists()


def test_upgrade_with_nothing_cached(
    cache: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opencode.upgrade_plugin()

    assert "No cached plugin found" in capsys.readouterr().out


def test_plugin_is_cached_needs_the_installed_package(cache: Path) -> None:
    assert not opencode._plugin_is_cached(cache)

    # A project OpenCode started but never finished installing does not count.
    (cache / "packages" / f"{PLUGIN}@latest").mkdir(parents=True)
    assert not opencode._plugin_is_cached(cache)

    _install_legacy(cache)
    assert opencode._plugin_is_cached(cache)


def test_plugin_is_cached_in_the_current_layout(cache: Path) -> None:
    _install_project(cache)
    assert opencode._plugin_is_cached(cache)


class _FakeNpm:
    def __init__(self, returncode: int = 0, raises: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.returncode = returncode
        self.raises = raises

    def __call__(self, cmd: list[str], **kwargs: Any) -> SimpleNamespace:
        self.calls.append({"cmd": cmd, **kwargs})
        if self.raises:
            raise self.raises
        return SimpleNamespace(returncode=self.returncode, stdout="", stderr="")


@pytest.fixture
def npm(monkeypatch: pytest.MonkeyPatch) -> _FakeNpm:
    fake = _FakeNpm()
    monkeypatch.setattr(
        opencode.shutil, "which", lambda name: "/fake/npm" if name == "npm" else None
    )
    monkeypatch.setattr(opencode.subprocess, "run", fake)
    return fake


def test_pre_install_skips_when_cached(cache: Path, npm: _FakeNpm) -> None:
    _install_project(cache)

    opencode._ensure_plugin_installed()

    assert npm.calls == []


def test_pre_install_targets_the_current_layout(cache: Path, npm: _FakeNpm) -> None:
    opencode._ensure_plugin_installed()

    assert len(npm.calls) == 1
    call = npm.calls[0]
    assert call["cmd"][:3] == ["/fake/npm", "install", f"{PLUGIN}@latest"]
    assert call["cwd"] == str(cache / "packages" / f"{PLUGIN}@latest")


def test_pre_install_runs_again_after_a_half_finished_install(
    cache: Path, npm: _FakeNpm
) -> None:
    (cache / "packages" / f"{PLUGIN}@latest").mkdir(parents=True)

    opencode._ensure_plugin_installed()

    assert len(npm.calls) == 1


@pytest.mark.parametrize(
    "fake",
    [_FakeNpm(returncode=1), _FakeNpm(raises=OSError("boom"))],
    ids=["npm-fails", "npm-missing-at-run"],
)
def test_failed_pre_install_leaves_no_project_behind(
    cache: Path, monkeypatch: pytest.MonkeyPatch, fake: _FakeNpm
) -> None:
    monkeypatch.setattr(opencode.shutil, "which", lambda _: "/fake/npm")
    monkeypatch.setattr(opencode.subprocess, "run", fake)

    opencode._ensure_plugin_installed()

    assert not (cache / "packages" / f"{PLUGIN}@latest").exists()
