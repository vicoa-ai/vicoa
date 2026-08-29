"""`find_npm_cli` must probe only the nvm-*default* node version.

The load-bearing case is `test_stale_global_in_old_version_is_not_found`: nvm
keeps every installed node version on disk, so a global CLI left behind in an
old, no-longer-selected version reads as "installed" if we scan them all — even
though the user's own `which <name>` (running the default version) can't see it.
That false positive is exactly what kept a since-removed agent showing as Ready
in the Providers list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vicoa import utils
from vicoa.utils import _nvm_default_node_bin, find_npm_cli


def _make_nvm(home: Path, versions: list[str], default: str) -> None:
    for version in versions:
        (home / ".nvm" / "versions" / "node" / version / "bin").mkdir(parents=True)
    alias = home / ".nvm" / "alias"
    alias.mkdir(parents=True)
    (alias / "default").write_text(default + "\n")


def _install_cli(home: Path, version: str, name: str) -> Path:
    path = home / ".nvm" / "versions" / "node" / version / "bin" / name
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    # Neutralize every other resolution path so the test isolates the nvm sweep:
    # nothing on PATH (also stops the `npm config get prefix` last resort) and no
    # nvm/npm env-var shortcuts.
    monkeypatch.setattr(utils.shutil, "which", lambda _name: None)
    monkeypatch.delenv("NVM_BIN", raising=False)
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)
    return tmp_path


def test_stale_global_in_old_version_is_not_found(home: Path):
    _make_nvm(home, ["v22.23.2", "v20.20.2"], default="22")
    _install_cli(home, "v20.20.2", "gemini")  # left over from the old node

    assert find_npm_cli("gemini") is None


def test_cli_in_default_version_is_found(home: Path):
    _make_nvm(home, ["v22.23.2", "v20.20.2"], default="22")
    expected = _install_cli(home, "v22.23.2", "gemini")

    assert find_npm_cli("gemini") == str(expected)


def test_default_alias_partial_picks_highest_matching(home: Path):
    _make_nvm(home, ["v22.23.2", "v22.9.0", "v20.20.2"], default="22")
    assert _nvm_default_node_bin(home / ".nvm") == (
        home / ".nvm" / "versions" / "node" / "v22.23.2" / "bin"
    )


def test_default_alias_exact_version(home: Path):
    _make_nvm(home, ["v22.23.2", "v20.20.2"], default="v20.20.2")
    assert _nvm_default_node_bin(home / ".nvm") == (
        home / ".nvm" / "versions" / "node" / "v20.20.2" / "bin"
    )


def test_default_alias_node_means_highest_installed(home: Path):
    _make_nvm(home, ["v22.23.2", "v20.20.2"], default="node")
    assert _nvm_default_node_bin(home / ".nvm") == (
        home / ".nvm" / "versions" / "node" / "v22.23.2" / "bin"
    )


def test_default_alias_chain_is_followed(home: Path):
    # `default -> lts/* -> lts/iron -> v20.20.2`, the shape nvm writes for
    # `nvm alias default 'lts/*'`.
    _make_nvm(home, ["v22.23.2", "v20.20.2"], default="lts/*")
    lts = home / ".nvm" / "alias" / "lts"
    lts.mkdir()
    (lts / "*").write_text("lts/iron\n")
    (lts / "iron").write_text("v20.20.2\n")

    assert _nvm_default_node_bin(home / ".nvm") == (
        home / ".nvm" / "versions" / "node" / "v20.20.2" / "bin"
    )


@pytest.mark.parametrize("versions", [["v22.23.2"], ["v22.23.2", "v20.20.2"]])
def test_no_default_alias_resolves_to_nothing(home: Path, versions: list[str]):
    # Without a `default` alias nvm wouldn't select a version for a login shell
    # either, so neither do we — whether one version is installed or several.
    # (`NVM_BIN` / PATH are tried earlier by `find_npm_cli`, not here.)
    for version in versions:
        (home / ".nvm" / "versions" / "node" / version / "bin").mkdir(parents=True)
    assert _nvm_default_node_bin(home / ".nvm") is None


def test_no_nvm_at_all_is_none(home: Path):
    assert _nvm_default_node_bin(home / ".nvm") is None
