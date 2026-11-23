"""Vicoa installs a pinned agent CLI build itself, for a machine with none.

Every download here comes from a local HTTP server; nothing touches the
network. The installer must only ever leave a verified, unpacked build in
place (``~/.vicoa/agents/<agent>/<version>/``), and detection and launch must
prefer the user's own install over that copy.
"""

from __future__ import annotations

import dataclasses
import errno
import hashlib
import io
import os
import re
import sys
import tarfile
import threading
import time
import zipfile
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

import pytest

from vicoa import agent_install, machine_daemon, utils
from vicoa.agent_install import (
    AgentInstaller,
    Host,
    InstallProgress,
    asset_key,
    is_managed_path,
    managed_cli_path,
)
from vicoa.agent_release_types import ArchiveKind, PinnedRelease, ReleaseAsset
from vicoa.agent_releases import PINNED_RELEASES
from vicoa.machine_daemon import MachineDaemon

MAC_ARM = Host(os="darwin", arch="arm64")
#: A build that passes the installer's trial run (`--version` exits 0).
RUNS = b"#!/bin/sh\necho 1.0.0\n"


# ----- a local server standing in for the vendors' download hosts -----


class _Files:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.hits: dict[str, int] = {}
        self.truncate: set[str] = set()
        self.hold: Optional[threading.Event] = None
        self.base = ""


@pytest.fixture
def server() -> Iterator[_Files]:
    state = _Files()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server's name
            state.hits[self.path] = state.hits.get(self.path, 0) + 1
            if state.hold is not None:
                state.hold.wait(5)
            body = state.files.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            short = self.path in state.truncate
            self.wfile.write(body[: len(body) // 2] if short else body)

        def log_message(self, *args: Any) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    state.base = f"http://127.0.0.1:{httpd.server_port}"
    yield state
    httpd.shutdown()
    httpd.server_close()


def _release(
    server: _Files,
    agent: str,
    payload: bytes,
    archive: ArchiveKind,
    binary: str,
    *,
    sha256: Optional[str] = None,
    fallback: bool = False,
    version: str = "1.0.0",
    size: Optional[int] = None,
) -> dict[str, PinnedRelease]:
    path = f"/{agent}/{version}/build"
    url = f"{server.base}{path}"
    fallback_url = None
    if fallback:
        # The first host doesn't have it; the second does.
        fallback_url = f"{server.base}/mirror{path}"
        server.files[f"/mirror{path}"] = payload
    else:
        server.files[path] = payload
    asset = ReleaseAsset(
        url=url,
        fallback_url=fallback_url,
        sha256=sha256 or hashlib.sha256(payload).hexdigest(),
        size=len(payload) if size is None else size,
        archive=archive,
        binary=binary,
    )
    return {
        agent: PinnedRelease(
            agent=agent, version=version, assets={asset_key(agent, MAC_ARM): asset}
        )
    }


def _tar_gz(files: dict[str, tuple[bytes, int]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, (data, mode) in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = mode
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _zip(files: dict[str, tuple[bytes, int]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, (data, mode) in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            zf.writestr(info, data)
    return buf.getvalue()


def _install(
    root: Path, releases: dict[str, PinnedRelease], agent: str
) -> tuple[InstallProgress, list[str]]:
    installed: list[str] = []
    installer = AgentInstaller(
        root=root, releases=releases, host=MAC_ARM, on_installed=installed.append
    )
    installer.start(agent)
    result = installer.wait(agent, timeout=10)
    assert result is not None
    return result, installed


def _nothing_installed(root: Path, agent: str) -> bool:
    agent_dir = root / agent
    return not agent_dir.exists() or not any(agent_dir.iterdir())


# ----- which build a machine takes -----


@pytest.mark.parametrize(
    ("host", "claude", "codex", "opencode"),
    [
        (MAC_ARM, "darwin-arm64", "aarch64-apple-darwin", "darwin-arm64"),
        (
            Host(os="darwin", arch="x64"),
            "darwin-x64",
            "x86_64-apple-darwin",
            "darwin-x64",
        ),
        (
            Host(os="linux", arch="x64", avx2=False),
            "linux-x64",
            "x86_64-unknown-linux-musl",
            "linux-x64-baseline",
        ),
        (
            Host(os="linux", arch="arm64", musl=True),
            "linux-arm64-musl",
            "aarch64-unknown-linux-musl",
            "linux-arm64-musl",
        ),
        (
            Host(os="windows", arch="x64"),
            "win32-x64",
            "x86_64-pc-windows-msvc",
            "windows-x64",
        ),
        (
            Host(os="windows", arch="arm64"),
            "win32-arm64",
            "aarch64-pc-windows-msvc",
            "windows-arm64",
        ),
    ],
)
def test_each_host_maps_to_the_vendors_own_build_name(
    host: Host, claude: str, codex: str, opencode: str
) -> None:
    assert asset_key("claude", host) == claude
    assert asset_key("codex", host) == codex
    assert asset_key("opencode", host) == opencode


def test_every_supported_host_has_a_pinned_build() -> None:
    hosts = [
        Host(os=os_name, arch=arch, musl=musl, avx2=avx2)
        for os_name in ("darwin", "linux", "windows")
        for arch in ("x64", "arm64")
        for musl in ((False, True) if os_name == "linux" else (False,))
        for avx2 in ((True, False) if arch == "x64" else (True,))
    ]
    for agent, release in PINNED_RELEASES.items():
        for host in hosts:
            assert asset_key(agent, host) in release.assets, (agent, host)  # type: ignore[arg-type]


def test_the_pinned_table_is_well_formed() -> None:
    # Which Claude Code build matches the SDK is the pin script's check: the
    # SDK here is whatever version this environment resolved, not a pin.
    for release in PINNED_RELEASES.values():
        for key, asset in release.assets.items():
            assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256), (release.agent, key)
            assert asset.size > 0
            assert asset.url.startswith("https://")
            assert asset.binary.endswith(".exe") == (
                key.startswith(("win32", "windows")) or "windows" in key
            )


# ----- installing -----


def test_installs_a_raw_build(server: _Files, tmp_path: Path) -> None:
    payload = RUNS
    releases = _release(server, "claude", payload, "raw", "claude")

    result, installed = _install(tmp_path, releases, "claude")

    assert result.phase == "installed", result
    binary = tmp_path / "claude" / "1.0.0" / "claude"
    assert result.path == str(binary)
    assert binary.read_bytes() == payload
    assert os.access(binary, os.X_OK)
    assert result.bytes_done == result.bytes_total == len(payload)
    assert installed == ["claude"]


def test_installs_a_tar_package_with_its_sidecars(
    server: _Files, tmp_path: Path
) -> None:
    payload = _tar_gz(
        {
            "codex-package.json": (b"{}", 0o644),
            "bin/codex": (RUNS, 0o755),
            "bin/codex-code-mode-host": (b"#!/bin/sh\n", 0o755),
        }
    )
    releases = _release(server, "codex", payload, "tar.gz", "bin/codex")

    result, _ = _install(tmp_path, releases, "codex")

    assert result.phase == "installed", result
    package = tmp_path / "codex" / "1.0.0"
    assert os.access(package / "bin" / "codex", os.X_OK)
    assert (package / "bin" / "codex-code-mode-host").is_file()
    assert not (package / "download").exists()


def test_installs_a_zip_and_makes_the_cli_executable(
    server: _Files, tmp_path: Path
) -> None:
    payload = _zip({"opencode": (RUNS, 0o644)})
    releases = _release(server, "opencode", payload, "zip", "opencode")

    result, _ = _install(tmp_path, releases, "opencode")

    assert result.phase == "installed", result
    assert os.access(tmp_path / "opencode" / "1.0.0" / "opencode", os.X_OK)


def test_uses_the_second_host_when_the_first_lacks_the_build(
    server: _Files, tmp_path: Path
) -> None:
    releases = _release(server, "claude", RUNS, "raw", "claude", fallback=True)

    result, _ = _install(tmp_path, releases, "claude")

    assert result.phase == "installed", result


def test_a_build_that_doesnt_match_its_checksum_is_rejected(
    server: _Files, tmp_path: Path
) -> None:
    releases = _release(server, "claude", b"tampered", "raw", "claude", sha256="0" * 64)

    result, installed = _install(tmp_path, releases, "claude")

    assert result.phase == "failed"
    assert result.error_code == "checksum_mismatch"
    assert _nothing_installed(tmp_path, "claude")
    assert installed == []


def test_a_download_that_stops_short_never_counts_as_installed(
    server: _Files, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releases = _release(server, "claude", b"x" * 100_000, "raw", "claude")
    server.truncate.add("/claude/1.0.0/build")

    result, installed = _install(tmp_path, releases, "claude")

    assert result.phase == "failed"
    assert result.error_code == "download_failed"
    assert _nothing_installed(tmp_path, "claude")
    assert installed == []


def test_an_archive_cannot_write_outside_its_folder(
    server: _Files, tmp_path: Path
) -> None:
    payload = _zip({"../escaped": (b"x", 0o644), "opencode": (b"x", 0o755)})
    root = tmp_path / "root"
    releases = _release(server, "opencode", payload, "zip", "opencode")

    result, _ = _install(root, releases, "opencode")

    assert result.phase == "failed"
    assert result.error_code == "unpack_failed"
    assert not list(tmp_path.rglob("escaped"))
    assert _nothing_installed(root, "opencode")


def test_two_requests_for_one_agent_share_one_download(
    server: _Files, tmp_path: Path
) -> None:
    releases = _release(server, "claude", RUNS, "raw", "claude")
    server.hold = threading.Event()
    installer = AgentInstaller(root=tmp_path, releases=releases, host=MAC_ARM)

    first = installer.start("claude")
    second = installer.start("claude")
    server.hold.set()
    result = installer.wait("claude", timeout=10)

    assert first.phase == second.phase == "downloading"
    assert result is not None and result.phase == "installed"
    assert server.hits == {"/claude/1.0.0/build": 1}


def _age(path: Path, seconds: float) -> None:
    then = time.time() - seconds
    for entry in [path, *path.rglob("*")]:
        os.utime(entry, (then, then))


def test_a_dead_install_is_swept_but_another_daemons_live_one_is_left(
    server: _Files, tmp_path: Path
) -> None:
    dead = tmp_path / "claude" / ".staging-1.0.0-dead"
    dead.mkdir(parents=True)
    (dead / "download").write_bytes(b"part")
    _age(dead, 3600)
    # Another daemon sharing this HOME, mid-download right now.
    live = tmp_path / "claude" / ".staging-1.0.0-live"
    live.mkdir()
    (live / "download").write_bytes(b"part")
    releases = _release(server, "claude", RUNS, "raw", "claude")

    result, _ = _install(tmp_path, releases, "claude")

    assert result.phase == "installed", result
    assert not dead.exists()
    assert live.is_dir()


def test_an_older_build_stays_until_the_next_start_tidies_it(
    server: _Files, tmp_path: Path
) -> None:
    for version in ("0.9.0", "2.0.0"):
        (tmp_path / "claude" / version).mkdir(parents=True)
        (tmp_path / "claude" / version / "claude").write_bytes(RUNS)
    releases = _release(server, "claude", RUNS, "raw", "claude")
    installer = AgentInstaller(root=tmp_path, releases=releases, host=MAC_ARM)

    installer.start("claude")
    assert (result := installer.wait("claude", timeout=10)) is not None
    assert result.phase == "installed", result
    # A session started on 0.9.0 while the new build downloaded may still run.
    assert (tmp_path / "claude" / "0.9.0").is_dir()

    installer.tidy()

    # 2.0.0 is a newer daemon release's (same HOME): not ours to remove.
    assert sorted(p.name for p in (tmp_path / "claude").iterdir()) == [
        "1.0.0",
        "2.0.0",
    ]


def test_tidy_keeps_an_older_build_while_the_pinned_one_is_missing(
    tmp_path: Path,
) -> None:
    old = tmp_path / "claude" / "0.9.0"
    old.mkdir(parents=True)
    (old / "claude").write_bytes(RUNS)
    (tmp_path / "claude" / ".trash-0.8.0-1-2").mkdir()
    releases = {
        "claude": PinnedRelease(
            agent="claude",
            version="1.0.0",
            assets={
                "darwin-arm64": ReleaseAsset(
                    url="https://example.invalid/claude",
                    sha256="0" * 64,
                    size=1,
                    archive="raw",
                    binary="claude",
                )
            },
        )
    }

    AgentInstaller(root=tmp_path, releases=releases, host=MAC_ARM).tidy()

    assert sorted(p.name for p in (tmp_path / "claude").iterdir()) == ["0.9.0"]


def test_a_version_dir_missing_its_cli_is_installed_afresh(
    server: _Files, tmp_path: Path
) -> None:
    broken = tmp_path / "claude" / "1.0.0"
    broken.mkdir(parents=True)
    (broken / "leftover").write_text("x")
    releases = _release(server, "claude", RUNS, "raw", "claude")

    result, _ = _install(tmp_path, releases, "claude")

    assert result.phase == "installed", result
    assert sorted(p.name for p in broken.iterdir()) == ["claude"]


def test_a_build_that_doesnt_run_here_is_not_installed(
    server: _Files, tmp_path: Path
) -> None:
    releases = _release(server, "claude", b"#!/bin/sh\nexit 3\n", "raw", "claude")

    result, installed = _install(tmp_path, releases, "claude")

    assert result.phase == "failed"
    assert result.error_code == "verify_failed"
    assert "exit code 3" in (result.error or "")
    assert _nothing_installed(tmp_path, "claude")
    assert installed == []


def test_the_trial_run_keeps_the_build_from_updating_itself(
    server: _Files, tmp_path: Path
) -> None:
    payload = b'#!/bin/sh\n[ "$DISABLE_AUTOUPDATER" = 1 ] || exit 9\n'
    releases = _release(server, "claude", payload, "raw", "claude")

    result, _ = _install(tmp_path, releases, "claude")

    assert result.phase == "installed", result


def test_a_download_larger_than_the_pin_is_cut_off(
    server: _Files, tmp_path: Path
) -> None:
    payload = RUNS + b"#" * 1000
    releases = _release(server, "claude", payload, "raw", "claude", size=len(RUNS))

    result, _ = _install(tmp_path, releases, "claude")

    assert result.phase == "failed"
    assert result.error_code == "checksum_mismatch"
    assert "larger" in (result.error or "")
    assert _nothing_installed(tmp_path, "claude")


@dataclasses.dataclass
class _Usage:
    free: int
    total: int = 0
    used: int = 0


def test_too_little_disk_space_is_refused_before_downloading(
    server: _Files, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releases = _release(server, "claude", RUNS, "raw", "claude")
    monkeypatch.setattr(
        agent_install.shutil, "disk_usage", lambda path: _Usage(free=1024)
    )

    result, _ = _install(tmp_path, releases, "claude")

    assert result.phase == "failed"
    assert result.error_code == "no_space"
    assert server.hits == {}


def test_a_disk_error_is_not_retried_on_the_second_host(
    server: _Files, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releases = _release(server, "claude", RUNS, "raw", "claude")
    release = releases["claude"]
    asset = release.assets["darwin-arm64"]
    server.files["/mirror/claude/1.0.0/build"] = RUNS
    releases = {
        "claude": dataclasses.replace(
            release,
            assets={
                "darwin-arm64": dataclasses.replace(
                    asset, fallback_url=f"{server.base}/mirror/claude/1.0.0/build"
                )
            },
        )
    }

    class _FullDisk(io.BytesIO):
        def write(self, data: Any) -> int:
            raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(
        agent_install, "open", lambda *a, **k: _FullDisk(), raising=False
    )

    result, _ = _install(tmp_path, releases, "claude")

    assert result.phase == "failed"
    assert result.error_code == "no_space"
    assert "/mirror/claude/1.0.0/build" not in server.hits


def test_a_stalled_download_fails(
    server: _Files, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releases = _release(server, "claude", RUNS, "raw", "claude")
    monkeypatch.setattr(agent_install, "_STALL_WINDOW_SECONDS", 0.0)
    monkeypatch.setattr(agent_install, "_STALL_MIN_BYTES", 1 << 30)

    result, _ = _install(tmp_path, releases, "claude")

    assert result.phase == "failed"
    assert result.error_code == "download_failed"
    assert "stalled" in (result.error or "")


def _tar_with_symlink() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("bin/codex")
        info.size = len(RUNS)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(RUNS))
        link = tarfile.TarInfo("bin/codex-alias")
        link.type = tarfile.SYMTYPE
        link.linkname = "codex"
        tar.addfile(link)
    return buf.getvalue()


def test_an_old_python_refuses_archive_links(
    server: _Files, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(tarfile, "data_filter", raising=False)
    releases = _release(server, "codex", _tar_with_symlink(), "tar.gz", "bin/codex")

    result, _ = _install(tmp_path, releases, "codex")

    assert result.phase == "failed"
    assert result.error_code == "unpack_failed"
    assert "link" in (result.error or "")


def test_an_old_python_still_unpacks_a_package_without_links(
    server: _Files, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(tarfile, "data_filter", raising=False)
    payload = _tar_gz({"bin/codex": (RUNS, 0o755)})
    releases = _release(server, "codex", payload, "tar.gz", "bin/codex")

    result, _ = _install(tmp_path, releases, "codex")

    assert result.phase == "installed", result


def test_a_failed_install_can_be_started_again(server: _Files, tmp_path: Path) -> None:
    releases = _release(server, "claude", RUNS, "raw", "claude")
    body = server.files.pop("/claude/1.0.0/build")
    installer = AgentInstaller(root=tmp_path, releases=releases, host=MAC_ARM)

    installer.start("claude")
    assert (first := installer.wait("claude", timeout=10)) is not None
    assert first.phase == "failed" and first.error_code == "download_failed"
    status = installer.status("claude")["claude"]
    assert status["phase"] == "failed"
    assert status["error_code"] == "download_failed"
    assert status["error"]

    server.files["/claude/1.0.0/build"] = body
    installer.start("claude")
    assert (second := installer.wait("claude", timeout=10)) is not None
    assert second.phase == "installed", second
    assert "error" not in installer.status("claude")["claude"]


def test_an_agent_with_no_build_for_this_machine_is_refused(tmp_path: Path) -> None:
    installer = AgentInstaller(
        root=tmp_path,
        releases={"claude": PinnedRelease(agent="claude", version="1.0.0", assets={})},
        host=MAC_ARM,
    )
    with pytest.raises(agent_install.InstallError) as excinfo:
        installer.start("claude")
    assert excinfo.value.code == "unsupported_platform"
    assert installer.offer("claude") is None


# ----- lookup: the user's own install first, then Vicoa's copy -----


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Sandbox home and PATH; pin the host so the real table applies."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(tmp_path / "user-bin"))
    monkeypatch.delenv("NVM_BIN", raising=False)
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(agent_install, "detect_host", lambda: MAC_ARM)
    # find_npm_cli also probes fixed system dirs (/usr/local/bin, linuxbrew,
    # snap): a real CLI there would beat the copy a test plants.
    real_resolve = utils._resolve_executable
    monkeypatch.setattr(
        utils,
        "_resolve_executable",
        lambda candidate: real_resolve(candidate)
        if str(candidate).startswith(str(tmp_path))
        else None,
    )
    return home


def _managed_copy(home: Path, agent: str) -> Path:
    release = PINNED_RELEASES[agent]
    binary = (
        home
        / ".vicoa"
        / "agents"
        / agent
        / release.version
        / release.assets[asset_key(agent, MAC_ARM)].binary
    )
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    return binary


def _user_install(tmp_path: Path, name: str) -> Path:
    binary = tmp_path / "user-bin" / name
    binary.parent.mkdir(exist_ok=True)
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    return binary


@pytest.mark.parametrize("agent", ["claude", "codex", "opencode"])
def test_vicoas_copy_is_found_when_the_user_has_none(
    fake_home: Path, agent: str
) -> None:
    managed = _managed_copy(fake_home, agent)
    assert managed_cli_path(agent) == str(managed)
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    assert daemon._check_agent_installation(agent) is None
    assert daemon._resolved_cli(agent) == str(managed)


@pytest.mark.parametrize("agent", ["claude", "codex", "opencode"])
def test_the_users_own_install_beats_vicoas_copy(
    fake_home: Path, tmp_path: Path, agent: str
) -> None:
    _managed_copy(fake_home, agent)
    own = _user_install(tmp_path, agent)
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    assert daemon._resolved_cli(agent) == str(own)
    assert not is_managed_path(str(own))


def test_a_build_from_an_earlier_release_still_counts(fake_home: Path) -> None:
    # A daemon upgrade that pins a newer version must not make a working
    # agent read as missing before the new build is installed.
    old = fake_home / ".vicoa" / "agents" / "opencode" / "1.0.0" / "opencode"
    old.parent.mkdir(parents=True)
    old.write_text("#!/bin/sh\n")
    assert utils.find_opencode_cli() == str(old)


# ----- launch: the command carries Vicoa's copy, which stays on its build -----


def test_a_claude_session_runs_vicoas_copy_with_self_update_off(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed = _managed_copy(fake_home, "claude")
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")

    source = daemon._build_headless_command(
        directory=os.getcwd(), agent="claude", session_id="s1", metadata=None
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    frozen = daemon._build_headless_command(
        directory=os.getcwd(), agent="claude", session_id="s1", metadata=None
    )
    env = daemon._session_env("claude", "s1")

    assert f"--claude-cli={managed}" in source
    assert f"--claude-cli={managed}" in frozen
    assert env["DISABLE_AUTOUPDATER"] == "1"


def test_an_opencode_session_on_vicoas_copy_keeps_its_build(fake_home: Path) -> None:
    managed = _managed_copy(fake_home, "opencode")
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    cmd = daemon._build_headless_command(
        directory=os.getcwd(), agent="opencode", session_id="s1", metadata=None
    )
    assert cmd[cmd.index("--opencode-command") + 1] == str(managed)
    assert daemon._session_env("opencode", "s1")["OPENCODE_DISABLE_AUTOUPDATE"] == "1"


def test_the_users_own_claude_is_left_to_the_sdk(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _user_install(tmp_path, "claude")
    monkeypatch.delenv("DISABLE_AUTOUPDATER", raising=False)
    # A pip/npm install: the SDK carries its own, version-matched build.
    monkeypatch.setattr(machine_daemon, "sdk_bundles_claude", lambda: True)
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    cmd = daemon._build_headless_command(
        directory=os.getcwd(), agent="claude", session_id="s1", metadata=None
    )
    assert not any(arg.startswith("--claude-cli") for arg in cmd)
    assert "DISABLE_AUTOUPDATER" not in daemon._session_env("claude", "s1")


def test_the_users_own_claude_is_handed_over_when_the_sdk_has_none(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The frozen daemon: no bundled build, and the SDK's own search covers far
    # fewer dirs than detection (npm prefix, winget links...).
    own = _user_install(tmp_path, "claude")
    monkeypatch.delenv("DISABLE_AUTOUPDATER", raising=False)
    monkeypatch.setattr(machine_daemon, "sdk_bundles_claude", lambda: False)
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    cmd = daemon._build_headless_command(
        directory=os.getcwd(), agent="claude", session_id="s1", metadata=None
    )
    assert f"--claude-cli={own}" in cmd
    # Still the user's own: it updates itself as it always has.
    assert "DISABLE_AUTOUPDATER" not in daemon._session_env("claude", "s1")


def test_npms_windows_shim_is_never_handed_to_the_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    monkeypatch.setattr(machine_daemon, "sdk_bundles_claude", lambda: False)
    monkeypatch.setattr(
        daemon,
        "_resolved_cli",
        lambda agent: r"C:\Users\a\AppData\Roaming\npm\claude.cmd",
    )
    with monkeypatch.context() as m:
        m.setattr(machine_daemon.sys, "platform", "win32")
        args = daemon._claude_cli_args()
    assert args == []


def test_the_claude_runner_takes_the_cli_it_is_handed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from integrations.headless import claude_code

    captured: dict[str, Any] = {}

    class FakeRunner:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def run(self) -> None:
            return None

    monkeypatch.setattr(claude_code, "HeadlessClaudeRunner", FakeRunner)
    monkeypatch.setattr(
        claude_code,
        "setup_logging",
        lambda *a, **k: __import__("logging").getLogger("t"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["claude_code", "--api-key", "k", "--claude-cli=/opt/claude/claude"],
    )
    claude_code.main()

    assert captured["cli_path"] == "/opt/claude/claude"
    # Declared, so it isn't passed on to the CLI as an extra flag.
    assert not any("claude-cli" in key for key in captured["extra_args"])


def test_the_sdk_options_carry_that_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.headless import claude_code
    from integrations.headless.claude_code import HeadlessClaudeRunner

    # Skip the log files and handlers setup_logging adds under the real HOME.
    monkeypatch.setattr(claude_code, "setup_logging", lambda *a, **k: None)
    runner = HeadlessClaudeRunner(
        vicoa_api_key="k",
        session_id="s1",
        cli_path="/opt/claude/claude",
        console_output=False,
    )
    assert str(runner._build_claude_options().cli_path) == "/opt/claude/claude"


# ----- the RPCs -----


def _daemon_with(
    installer: AgentInstaller, monkeypatch: pytest.MonkeyPatch
) -> MachineDaemon:
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    monkeypatch.setattr(daemon, "_agent_installer", installer)
    return daemon


def test_install_rpc_refuses_an_agent_it_cannot_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    daemon = _daemon_with(AgentInstaller(root=tmp_path), monkeypatch)
    assert (
        daemon.agent_install_rpc({"agent": "gemini"})["error_code"] == "unknown_agent"
    )
    assert daemon.agent_install_rpc({})["error_code"] == "unknown_agent"


def test_install_rpc_answers_installed_when_the_machine_has_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    daemon = _daemon_with(AgentInstaller(root=tmp_path), monkeypatch)
    monkeypatch.setattr(daemon, "_check_agent_installation", lambda agent: None)
    monkeypatch.setattr(daemon, "_resolved_cli", lambda agent: "/usr/bin/codex")

    result = daemon.agent_install_rpc({"agent": "codex"})

    assert result == {
        "agent": "codex",
        "phase": "installed",
        "path": "/usr/bin/codex",
        "already_installed": True,
    }


def test_install_rpc_starts_in_the_background_and_republishes_when_done(
    server: _Files, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releases = _release(server, "claude", RUNS, "raw", "claude")
    published: list[dict[str, bool]] = []
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    installer = AgentInstaller(
        root=tmp_path,
        releases=releases,
        host=MAC_ARM,
        on_installed=daemon._on_agent_installed,
    )
    monkeypatch.setattr(daemon, "_agent_installer", installer)
    monkeypatch.setattr(daemon, "_check_agent_installation", lambda agent: "missing")
    monkeypatch.setattr(daemon, "_detect_available_agents", lambda: {"claude": True})
    monkeypatch.setattr(daemon, "push_available_agents", published.append)
    server.hold = threading.Event()

    started = daemon.agent_install_rpc({"agent": "claude"})
    assert started["phase"] == "downloading"
    assert started["bytes_total"] == len(RUNS)
    in_flight = daemon.agent_install_status_rpc({"agent": "claude"})
    assert in_flight["installs"]["claude"]["phase"] == "downloading"
    assert in_flight["installs"]["claude"]["bytes_total"] == len(RUNS)
    # Nothing is in place until the final rename.
    assert "managed_version" not in in_flight["installable"]["claude"]

    server.hold.set()
    installer.wait("claude", timeout=10)
    status = daemon.agent_install_status_rpc({"agent": "claude"})

    assert status["installable"] == {
        "claude": {"version": "1.0.0", "size": len(RUNS), "managed_version": "1.0.0"}
    }
    assert status["installs"]["claude"]["phase"] == "installed"
    assert published == [{"claude": True}]


def test_the_daemon_advertises_the_install_rpcs() -> None:
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    assert "agent-install" in daemon._capabilities()
    assert {"agent-install", "agent-install-status"} <= set(
        daemon._supported_rpc_methods()
    )
    for method in ("agent-install", "agent-install-status"):
        result = daemon._handle_rpc_request(
            {"method": method, "params": {"agent": "not-an-agent"}}
        )
        assert isinstance(result, dict)


def test_install_status_offers_every_agent_this_machine_can_take(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    daemon = _daemon_with(AgentInstaller(root=tmp_path, host=MAC_ARM), monkeypatch)
    offers = daemon.agent_install_status_rpc({})["installable"]
    assert set(offers) == {"claude", "codex", "opencode"}
    assert offers["claude"]["version"] == PINNED_RELEASES["claude"].version
    assert (
        offers["codex"]["size"]
        == PINNED_RELEASES["codex"].assets["aarch64-apple-darwin"].size
    )


# ----- which machine this is -----


@pytest.mark.parametrize(
    ("sys_platform", "machine", "env", "probes", "expected"),
    [
        ("darwin", "arm64", {}, {}, Host(os="darwin", arch="arm64")),
        # An x64 daemon under Rosetta takes the native build.
        ("darwin", "x86_64", {}, {"rosetta": True}, Host(os="darwin", arch="arm64")),
        (
            "darwin",
            "x86_64",
            {},
            {"avx2": False},
            Host(os="darwin", arch="x64", avx2=False),
        ),
        (
            "linux",
            "aarch64",
            {},
            {"musl": True},
            Host(os="linux", arch="arm64", musl=True),
        ),
        ("linux", "x86_64", {}, {}, Host(os="linux", arch="x64")),
        # x64 Python on Windows on ARM: the OS's own answer wins.
        (
            "win32",
            "AMD64",
            {"PROCESSOR_ARCHITECTURE": "AMD64", "PROCESSOR_ARCHITEW6432": "ARM64"},
            {},
            Host(os="windows", arch="arm64"),
        ),
        (
            "win32",
            "AMD64",
            {"PROCESSOR_ARCHITECTURE": "AMD64"},
            {},
            Host(os="windows", arch="x64"),
        ),
        ("freebsd14", "amd64", {}, {}, None),
        ("linux", "riscv64", {}, {}, None),
    ],
)
def test_the_host_is_read_from_the_os_and_cpu(
    monkeypatch: pytest.MonkeyPatch,
    sys_platform: str,
    machine: str,
    env: dict[str, str],
    probes: dict[str, bool],
    expected: Optional[Host],
) -> None:
    monkeypatch.setattr(
        agent_install, "_is_rosetta", lambda: probes.get("rosetta", False)
    )
    monkeypatch.setattr(agent_install, "_is_musl", lambda: probes.get("musl", False))
    monkeypatch.setattr(
        agent_install, "_has_avx2", lambda os_name: probes.get("avx2", True)
    )
    assert agent_install._host_from(sys_platform, machine, env) == expected


def test_this_machine_is_a_host_with_builds() -> None:
    agent_install.detect_host.cache_clear()
    try:
        host = agent_install.detect_host()
    finally:
        agent_install.detect_host.cache_clear()
    assert host is not None
    assert agent_install.has_build_for_this_host()


# ----- upgrades: Vicoa's copy follows the pin, the user's install is left be -----


def _old_managed_copy(home: Path, agent: str, version: str) -> Path:
    asset = PINNED_RELEASES[agent].assets[asset_key(agent, MAC_ARM)]
    binary = home / ".vicoa" / "agents" / agent / version / asset.binary
    binary.parent.mkdir(parents=True)
    binary.write_bytes(RUNS)
    binary.chmod(0o755)
    return binary


def _pinned_opencode(server: _Files) -> dict[str, PinnedRelease]:
    """The real pinned OpenCode version, served from the local server."""
    return _release(
        server,
        "opencode",
        _zip({"opencode": (RUNS, 0o755)}),
        "zip",
        "opencode",
        version=PINNED_RELEASES["opencode"].version,
    )


def _upgrading_daemon(
    server: _Files, home: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[MachineDaemon, AgentInstaller, list[dict[str, bool]]]:
    published: list[dict[str, bool]] = []
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    installer = AgentInstaller(
        root=home / ".vicoa" / "agents",
        releases=_pinned_opencode(server),
        host=MAC_ARM,
        on_installed=daemon._on_agent_installed,
    )
    monkeypatch.setattr(daemon, "_agent_installer", installer)
    monkeypatch.setattr(daemon, "_detect_available_agents", lambda: {"opencode": True})
    monkeypatch.setattr(daemon, "push_available_agents", published.append)
    return daemon, installer, published


def test_install_rpc_upgrades_vicoas_copy_from_an_older_release(
    server: _Files, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _old_managed_copy(fake_home, "opencode", "0.0.1")
    daemon, installer, published = _upgrading_daemon(server, fake_home, monkeypatch)
    assert daemon._resolved_cli("opencode") == str(old)

    offer = daemon.agent_install_status_rpc({"agent": "opencode"})["installable"]
    assert offer["opencode"]["managed_version"] == "0.0.1"
    assert offer["opencode"]["version"] == PINNED_RELEASES["opencode"].version

    started = daemon.agent_install_rpc({"agent": "opencode"})
    assert "already_installed" not in started
    assert (done := installer.wait("opencode", timeout=10)) is not None
    assert done.phase == "installed", done

    pinned = str(old).replace("0.0.1", PINNED_RELEASES["opencode"].version)
    assert daemon._resolved_cli("opencode") == pinned
    assert published == [{"opencode": True}]
    # Kept for a session that may still run it; the next start removes it.
    assert old.is_file()
    installer.tidy()
    assert not old.parent.exists()


def test_the_daemon_upgrades_vicoas_copy_by_itself_at_start(
    server: _Files, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _old_managed_copy(fake_home, "opencode", "0.0.1")
    daemon, installer, _ = _upgrading_daemon(server, fake_home, monkeypatch)

    daemon._upgrade_managed_agents()

    assert (done := installer.wait("opencode", timeout=10)) is not None
    assert done.phase == "installed", done


def test_a_newer_copy_from_another_daemon_release_is_not_downgraded(
    server: _Files, fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _old_managed_copy(fake_home, "opencode", "999.0.0")
    daemon, installer, _ = _upgrading_daemon(server, fake_home, monkeypatch)

    daemon._upgrade_managed_agents()
    result = daemon.agent_install_rpc({"agent": "opencode"})

    assert result["already_installed"] is True
    assert installer.status() == {}
    assert server.hits == {}


def test_the_users_own_install_is_never_upgraded(
    server: _Files, fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _old_managed_copy(fake_home, "opencode", "0.0.1")
    own = _user_install(tmp_path, "opencode")
    daemon, installer, _ = _upgrading_daemon(server, fake_home, monkeypatch)

    daemon._upgrade_managed_agents()
    result = daemon.agent_install_rpc({"agent": "opencode"})

    assert result == {
        "agent": "opencode",
        "phase": "installed",
        "path": str(own),
        "already_installed": True,
    }
    assert installer.status() == {}
    assert server.hits == {}


def test_install_rpc_answers_installed_for_the_pinned_copy(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed = _managed_copy(fake_home, "opencode")

    def no_network(url: str) -> Any:
        raise AssertionError(f"downloaded {url}")

    daemon = _daemon_with(AgentInstaller(host=MAC_ARM, opener=no_network), monkeypatch)
    result = daemon.agent_install_rpc({"agent": "opencode"})

    assert result["already_installed"] is True
    assert result["path"] == str(managed)


def test_install_rpc_leaves_a_user_install_without_a_managed_dir(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    own = _user_install(tmp_path, "codex")
    daemon = _daemon_with(AgentInstaller(host=MAC_ARM), monkeypatch)

    result = daemon.agent_install_rpc({"agent": "codex"})
    status = daemon.agent_install_status_rpc({"agent": "codex"})

    assert result["already_installed"] is True and result["path"] == str(own)
    assert not (fake_home / ".vicoa" / "agents").exists()
    # Still offered (a user may want Vicoa's copy), with nothing running.
    assert "managed_version" not in status["installable"]["codex"]
    assert status["installs"] == {}


def test_a_leftover_staging_dir_counts_for_nothing(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = fake_home / ".vicoa" / "agents" / "codex" / ".staging-0.1-x"
    staging.mkdir(parents=True)
    (staging / "content").mkdir()
    daemon = _daemon_with(AgentInstaller(host=MAC_ARM), monkeypatch)

    status = daemon.agent_install_status_rpc({"agent": "codex"})

    assert status["installs"] == {}
    assert "managed_version" not in status["installable"]["codex"]
    assert daemon._check_agent_installation("codex") is not None


# ----- one spawn looks each CLI up once -----


def test_one_spawn_looks_the_cli_up_once(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def find_codex() -> str:
        calls.append("codex")
        return "/opt/codex/codex"

    monkeypatch.setattr(machine_daemon, "find_codex_cli", find_codex)
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")

    assert daemon._check_agent_installation("codex") is None
    daemon._build_headless_command(
        directory=os.getcwd(), agent="codex", session_id="s1", metadata=None
    )
    daemon._session_env("codex", "s1")
    assert calls == ["codex"]

    # A scan (the Rescan button, registration) always looks again.
    daemon._detect_available_agents()
    assert calls == ["codex", "codex"]
