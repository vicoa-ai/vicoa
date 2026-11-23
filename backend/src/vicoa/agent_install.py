"""Agent CLIs Vicoa installs itself, for a machine that has none of its own.

The daemon downloads the build pinned in :mod:`vicoa.agent_releases` straight
from the vendor (no install script, no shell, no PATH edit), checks its size
and SHA-256, unpacks it and moves it into place in one rename:

    ~/.vicoa/agents/<agent>/<version>/<binary>

Nothing under that directory is ever half-written: a download lands in a
``.staging-*`` sibling first and only a verified, unpacked build is renamed to
its version directory, so the presence of that directory is the proof the
install finished.

The user's own install always comes first. Detection and launch look here only
when the agent can't be found anywhere else (see ``vicoa.utils.find_codex_cli``,
``find_opencode_cli`` and ``find_claude_cli``).

A daemon release that pins a newer build upgrades Vicoa's copy by itself (see
``MachineDaemon._upgrade_managed_agents``): the managed copy has self-update
turned off, so nothing else would. The older build keeps serving until the new
one is in place, and is deleted at a later daemon start (:meth:`AgentInstaller.tidy`)
once no running process uses it: sessions outlive a daemon restart.
"""

from __future__ import annotations

import errno
import functools
import hashlib
import http.client
import importlib.util
import json
import logging
import os
import platform
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO, Literal, Optional

import certifi

from vicoa.agent_release_types import PinnedRelease, ReleaseAsset
from vicoa.agent_releases import PINNED_RELEASES

logger = logging.getLogger(__name__)

#: The agents this daemon release can install.
MANAGED_AGENTS: tuple[str, ...] = tuple(PINNED_RELEASES)

#: Environment that keeps a managed copy on its pinned build. Each CLI would
#: otherwise update itself in place, outside the version this release tested.
SELF_UPDATE_OFF: Mapping[str, Mapping[str, str]] = {
    "claude": {"DISABLE_AUTOUPDATER": "1"},
    "opencode": {"OPENCODE_DISABLE_AUTOUPDATE": "1"},
}

_CHUNK = 1 << 16
_USER_AGENT = "vicoa-agent-installer"
_STAGING_PREFIX = ".staging-"
_TRASH_PREFIX = ".trash-"

#: A staging dir untouched this long belongs to an install that died; a live
#: one is written to continuously (the download, then the unpacked files).
_STALE_STAGING_SECONDS = 15 * 60
#: A download slower than this many bytes per window is treated as stuck. A
#: dead connection already fails on the socket timeout; this catches a trickle.
_STALL_WINDOW_SECONDS = 120.0
_STALL_MIN_BYTES = 256 * 1024
#: How long the new build's ``--version`` may take. Generous: the first run of
#: a fresh executable on Windows waits for the antivirus scan.
_VERSION_CHECK_TIMEOUT = 120
#: Headroom kept free on top of the install itself.
_SPACE_MARGIN = 64 * 1024 * 1024
#: An unpacked archive takes a few times its download size; the vendors' own
#: packages run 2-3x.
_ARCHIVE_EXPANSION = 4

Phase = Literal["downloading", "verifying", "unpacking", "installed", "failed"]
ErrorCode = Literal[
    "unknown_agent",
    "unsupported_platform",
    "download_failed",
    "checksum_mismatch",
    "unpack_failed",
    #: The unpacked build didn't run (``--version`` failed).
    "verify_failed",
    "no_space",
    #: Writing to this machine's disk failed (not the network).
    "write_failed",
]
#: Failures on this machine's side: another download host can't help.
_LOCAL_FAILURES: frozenset[str] = frozenset({"no_space", "write_failed"})
#: Failures that downloading the same build again won't change. After one, the
#: daemon stops upgrading to that build by itself at every start (each try is
#: a full download); an explicit Install still tries it.
_NO_AUTO_RETRY: frozenset[str] = frozenset({"verify_failed", "checksum_mismatch"})
#: Per agent dir: the pinned version whose install hit a _NO_AUTO_RETRY failure.
_AUTO_UPGRADE_BLOCK = ".auto-upgrade-blocked"


def agents_root() -> Path:
    """Where managed agent CLIs live."""
    return Path.home() / ".vicoa" / "agents"


# ----- the host -----------------------------------------------------------


@dataclass(frozen=True)
class Host:
    """What decides which build of an agent this machine takes."""

    os: Literal["darwin", "linux", "windows"]
    arch: Literal["x64", "arm64"]
    #: Linux with musl libc rather than glibc.
    musl: bool = False
    #: x64 with AVX2; without it some vendors ship a "baseline" build.
    avx2: bool = True


def _run_quietly(args: list[str]) -> str:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=5, check=False
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _is_rosetta() -> bool:
    """An x64 process on an Apple-silicon Mac: install the native arm64 build."""
    return _run_quietly(["sysctl", "-n", "sysctl.proc_translated"]) == "1"


def _is_musl() -> bool:
    """Whether this Linux runs musl libc rather than glibc.

    The running interpreter answers first: a daemon linked against glibc is on
    a glibc system, whatever else is installed. The files are the vendors' own
    fallback signals (Alpine's libc, /etc/alpine-release). musl's loader,
    /lib/ld-musl-*.so.1, is deliberately not one: a glibc distro with the musl
    package installed has it too, and would be handed a build it can't run.
    """
    libc, _ = platform.libc_ver()
    if libc == "glibc":
        return False
    if libc == "musl":
        return True
    return (
        any(Path("/lib").glob("libc.musl-*.so.1"))
        or Path("/etc/alpine-release").exists()
    )


def _has_avx2(os_name: str) -> bool:
    """Best effort; an unknown answer picks the build that runs everywhere."""
    if os_name == "linux":
        try:
            return "avx2" in Path("/proc/cpuinfo").read_text().split()
        except OSError:
            return False
    if os_name == "darwin":
        return _run_quietly(["sysctl", "-n", "hw.optional.avx2_0"]) == "1"
    if os_name == "windows":
        try:
            import ctypes

            # PF_AVX2_INSTRUCTIONS_AVAILABLE
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - a failed probe means "don't know"
            return False
    return False


@functools.lru_cache(maxsize=1)
def detect_host() -> Optional[Host]:
    """This machine, or None on an OS or CPU no vendor builds for."""
    return _host_from(sys.platform, platform.machine(), os.environ)


def _host_from(
    sys_platform: str, machine: str, env: Mapping[str, str]
) -> Optional[Host]:
    if sys_platform == "darwin":
        os_name: Literal["darwin", "linux", "windows"] = "darwin"
    elif sys_platform.startswith("linux"):
        os_name = "linux"
    elif sys_platform == "win32":
        os_name = "windows"
    else:
        return None

    machine = machine.lower()
    if os_name == "windows":
        # An x64 Python on Windows on ARM reports AMD64; the OS knows better.
        native = (
            env.get("PROCESSOR_ARCHITEW6432")
            or env.get("PROCESSOR_ARCHITECTURE")
            or machine
        )
        machine = native.lower()
    if machine in ("arm64", "aarch64"):
        arch: Literal["x64", "arm64"] = "arm64"
    elif machine in ("x86_64", "amd64", "x64"):
        arch = "x64"
    else:
        return None
    if os_name == "darwin" and arch == "x64" and _is_rosetta():
        arch = "arm64"

    return Host(
        os=os_name,
        arch=arch,
        musl=os_name == "linux" and _is_musl(),
        avx2=arch != "x64" or _has_avx2(os_name),
    )


def asset_key(agent: str, host: Host) -> str:
    """The vendor's own name for ``host``'s build of ``agent``."""
    if agent == "claude":
        os_part = "win32" if host.os == "windows" else host.os
        return f"{os_part}-{host.arch}" + ("-musl" if host.musl else "")
    if agent == "codex":
        cpu = "aarch64" if host.arch == "arm64" else "x86_64"
        rest = {
            "darwin": "apple-darwin",
            # Codex's Linux builds are static musl binaries for every libc.
            "linux": "unknown-linux-musl",
            "windows": "pc-windows-msvc",
        }[host.os]
        return f"{cpu}-{rest}"
    if agent == "opencode":
        key = f"{host.os}-{host.arch}"
        if host.arch == "x64" and not host.avx2:
            key += "-baseline"
        if host.musl:
            key += "-musl"
        return key
    raise KeyError(agent)


# ----- progress -----------------------------------------------------------


@dataclass
class InstallProgress:
    """One install, readable while it runs. ``to_dict`` is the RPC shape."""

    agent: str
    version: str
    phase: Phase
    bytes_done: int = 0
    bytes_total: Optional[int] = None
    #: The CLI's path once installed.
    path: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[ErrorCode] = None

    def to_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class InstallError(Exception):
    """An install that can't go on, with a stable code for clients."""

    def __init__(
        self, code: ErrorCode, message: str, *, transient: bool = False
    ) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        #: Might go away on a retry (a timeout, a file briefly held by an
        #: antivirus scan): never blocks the automatic upgrade.
        self.transient = transient


@dataclass(frozen=True)
class ManagedCopy:
    """A build of an agent CLI that Vicoa installed under the agents root."""

    version: str
    path: str
    #: Whether it is the build this daemon release pins.
    pinned: bool


Opener = Callable[[str], AbstractContextManager[IO[bytes]]]
#: Runs a freshly unpacked CLI once; raises :class:`InstallError` if it can't.
BuildCheck = Callable[[str, Path], None]
#: Every running process's command line, or None when they can't be listed.
CommandLines = Callable[[], Optional[list[str]]]


@functools.lru_cache(maxsize=1)
def _tls_context() -> ssl.SSLContext:
    """certifi's CA bundle, as the daemon's other HTTPS clients use.

    A frozen build's OpenSSL may not find the system CA store, and urllib's
    default context would then fail every download with
    CERTIFICATE_VERIFY_FAILED.
    """
    return ssl.create_default_context(cafile=certifi.where())


def _urlopen(url: str) -> AbstractContextManager[IO[bytes]]:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    return urllib.request.urlopen(  # noqa: S310 - pinned https URLs
        request, timeout=60, context=_tls_context()
    )


# ----- the installer --------------------------------------------------------


@dataclass
class _Running:
    progress: InstallProgress
    thread: Optional[threading.Thread] = None
    done: threading.Event = field(default_factory=threading.Event)


class AgentInstaller:
    """Installs pinned agent CLI builds; one install per agent at a time."""

    def __init__(
        self,
        *,
        root: Optional[Path] = None,
        releases: Optional[Mapping[str, PinnedRelease]] = None,
        host: Optional[Host] = None,
        opener: Optional[Opener] = None,
        check_build: Optional[BuildCheck] = None,
        running_commands: Optional[CommandLines] = None,
        on_installed: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._root = root
        self._releases = releases if releases is not None else PINNED_RELEASES
        self._host = host
        self._opener: Opener = opener or _urlopen
        self._check_build: BuildCheck = check_build or _check_build_runs
        self._running_commands: CommandLines = running_commands or _running_commands
        self._on_installed = on_installed
        self._lock = threading.Lock()
        self._installs: dict[str, _Running] = {}

    @property
    def root(self) -> Path:
        # Resolved late: HOME can differ between construction and use (tests,
        # a daemon whose HOME is set after import).
        return self._root if self._root is not None else agents_root()

    def _resolve(self, agent: str) -> tuple[PinnedRelease, ReleaseAsset]:
        release = self._releases.get(agent)
        if release is None:
            raise InstallError("unknown_agent", f"Vicoa can't install '{agent}'.")
        host = self._host or detect_host()
        asset = release.assets.get(asset_key(agent, host)) if host else None
        if asset is None:
            raise InstallError(
                "unsupported_platform",
                f"There is no {agent} build for this computer.",
            )
        return release, asset

    def offer(self, agent: str) -> Optional[dict[str, object]]:
        """What installing ``agent`` here means, or None if it can't be.

        ``version`` and ``size`` are the pinned build's; ``managed_version`` is
        the build of Vicoa's copy already here, when there is one.
        """
        try:
            release, asset = self._resolve(agent)
        except InstallError:
            return None
        offer: dict[str, object] = {"version": release.version, "size": asset.size}
        copy = self.managed_copy(agent)
        if copy is not None:
            offer["managed_version"] = copy.version
        return offer

    def managed_copy(self, agent: str) -> Optional[ManagedCopy]:
        """Vicoa's installed copy of ``agent``: the pinned build, else the newest."""
        return _find_managed_copy(
            agent,
            root=self.root,
            releases=self._releases,
            host=self._host or detect_host(),
        )

    def outdated_copy(self, agent: str) -> Optional[ManagedCopy]:
        """Vicoa's copy of ``agent`` when it is older than the pinned build.

        Only older: a newer one came from a newer daemon release sharing this
        HOME, and installing our older pin next to it would have the two
        daemons take turns downloading.
        """
        copy = self.managed_copy(agent)
        release = self._releases.get(agent)
        if copy is None or release is None or copy.pinned:
            return None
        if _version_key(copy.version) >= _version_key(release.version):
            return None
        return copy

    def tidy(self) -> None:
        """Daemon-start housekeeping under the agents root.

        Drops what dead installs left (staging and trash dirs) and, once the
        pinned build is in place, the older builds it replaced, except one a
        running process still uses: sessions are started in their own process
        group and outlive a daemon restart, and one may be on an older build.
        Such a build is kept for a later start.
        """
        command_lines: Optional[list[str]] = None
        listed = False
        for agent, release in self._releases.items():
            agent_dir = self.root / agent
            if not agent_dir.is_dir():
                continue
            _sweep_leftovers(agent_dir)
            copy = self.managed_copy(agent)
            if copy is None or not copy.pinned:
                continue
            older = _older_versions(agent_dir, release.version)
            if not older:
                continue
            if not listed:
                command_lines, listed = self._running_commands(), True
            if command_lines is None:
                # Can't tell what is running: keep everything until next time.
                logger.info("not removing older %s builds: can't list processes", agent)
                continue
            for entry in older:
                if _in_use(entry, command_lines):
                    logger.info("keeping %s: a running process uses it", entry)
                    continue
                _discard(entry)

    def auto_upgrade_blocked(self, agent: str) -> bool:
        """Whether installing ``agent``'s pinned build failed here in a way a
        new download won't fix (it didn't run, or didn't match its checksum)."""
        release = self._releases.get(agent)
        if release is None:
            return False
        try:
            data = json.loads((self.root / agent / _AUTO_UPGRADE_BLOCK).read_text())
        except (OSError, ValueError):
            return False
        return isinstance(data, dict) and data.get("version") == release.version

    def start(self, agent: str) -> InstallProgress:
        """Start installing ``agent`` in the background; return where it stands.

        A second call while one runs joins it rather than downloading twice.
        Raises :class:`InstallError` when the agent can't be installed here.
        """
        release, asset = self._resolve(agent)
        with self._lock:
            running = self._installs.get(agent)
            if running is not None and not running.done.is_set():
                return _snapshot(running.progress)
            progress = InstallProgress(
                agent=agent,
                version=release.version,
                phase="downloading",
                bytes_total=asset.size,
            )
            running = _Running(progress=progress)
            running.thread = threading.Thread(
                target=self._run,
                args=(running, release, asset),
                name=f"vicoa-install-{agent}",
                daemon=True,
            )
            self._installs[agent] = running
            running.thread.start()
        return _snapshot(progress)

    def wait(
        self, agent: str, timeout: Optional[float] = None
    ) -> Optional[InstallProgress]:
        """Block until ``agent``'s install (if any) finishes; return its result."""
        with self._lock:
            running = self._installs.get(agent)
        if running is None:
            return None
        running.done.wait(timeout)
        return _snapshot(running.progress)

    def status(self, agent: Optional[str] = None) -> dict[str, dict[str, object]]:
        """Every install this daemon has run or is running, by agent."""
        with self._lock:
            items = [
                (name, running.progress)
                for name, running in self._installs.items()
                if agent is None or name == agent
            ]
        return {name: _snapshot(progress).to_dict() for name, progress in items}

    def _run(
        self, running: _Running, release: PinnedRelease, asset: ReleaseAsset
    ) -> None:
        # Status is read field by field while this runs, so each outcome's
        # details are set before the phase that announces it.
        progress = running.progress
        block = self.root / release.agent / _AUTO_UPGRADE_BLOCK
        try:
            try:
                path = self._install(release, asset, progress)
            except InstallError as exc:
                if exc.code in _NO_AUTO_RETRY and not exc.transient:
                    _write_quietly(
                        block, {"version": release.version, "error_code": exc.code}
                    )
                progress.error_code, progress.error = exc.code, exc.message
                progress.phase = "failed"
                return
            except OSError as exc:
                # Setting up dirs on this disk (mkdir, mkdtemp, chmod): not the
                # network, whatever happens to fail.
                local = _local_failure(exc)
                progress.error_code, progress.error = local.code, local.message
                progress.phase = "failed"
                return
            except Exception as exc:  # noqa: BLE001 - surface anything as a failed install
                logger.exception("installing %s failed", release.agent)
                progress.error_code = "download_failed"
                progress.error = f"Couldn't install {release.agent}: {exc}"
                progress.phase = "failed"
                return
            progress.path = str(path)
            try:
                block.unlink(missing_ok=True)
            except OSError:
                logger.warning("couldn't clear %s", block, exc_info=True)
            # Published before the install reads as done, so a client that
            # polls status and then reads the machine finds the agent there.
            if self._on_installed is not None:
                try:
                    self._on_installed(release.agent)
                except Exception:  # noqa: BLE001 - the install itself succeeded
                    logger.warning(
                        "post-install hook for %s failed",
                        release.agent,
                        exc_info=True,
                    )
            progress.phase = "installed"
        finally:
            running.done.set()

    def _install(
        self, release: PinnedRelease, asset: ReleaseAsset, progress: InstallProgress
    ) -> Path:
        agent_dir = self.root / release.agent
        final = agent_dir / release.version
        if (final / asset.binary).is_file():
            return final / asset.binary
        agent_dir.mkdir(parents=True, exist_ok=True)
        _sweep_leftovers(agent_dir)
        if (final / asset.binary).is_file():
            # Another daemon sharing this HOME finished it meanwhile.
            return final / asset.binary
        if final.exists():
            # A version dir without its CLI can't have come from the rename
            # (that is all or nothing), so something outside removed files.
            # Clear it now: the rename below can't replace a non-empty dir.
            _discard(final)
        _check_free_space(agent_dir, asset, release.agent)

        staging = Path(
            tempfile.mkdtemp(
                prefix=f"{_STAGING_PREFIX}{release.version}-", dir=agent_dir
            )
        )
        try:
            download = staging / "download"
            self._download(asset, download, progress)
            progress.phase = "unpacking"
            content = staging / "content"
            content.mkdir()
            _unpack(asset, download, content)
            download.unlink(missing_ok=True)
            binary = content / asset.binary
            if not binary.is_file():
                raise InstallError(
                    "unpack_failed",
                    f"The {release.agent} download had no {asset.binary} in it.",
                )
            if os.name != "nt":
                binary.chmod(0o755)
            # A build that can't start here (wrong libc or CPU, blocked by
            # security software) would otherwise read as installed and fail
            # every session instead.
            self._check_build(release.agent, binary)
            try:
                _replace(content, final)
            except OSError as exc:
                # Another daemon finished the same version first: theirs stands.
                if not (final / asset.binary).is_file():
                    raise InstallError(
                        "unpack_failed",
                        f"Couldn't move the {release.agent} build into place: {exc}",
                    ) from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        # Older builds stay until the next daemon start (see `tidy`): a
        # session launched before this install finished may be running one.
        return final / asset.binary

    def _download(
        self, asset: ReleaseAsset, dest: Path, progress: InstallProgress
    ) -> None:
        urls = [asset.url] + ([asset.fallback_url] if asset.fallback_url else [])
        failure: Optional[InstallError] = None
        for url in urls:
            try:
                self._fetch(url, asset, dest, progress)
                return
            except InstallError as exc:
                if exc.code in _LOCAL_FAILURES:
                    raise
                failure = exc
            dest.unlink(missing_ok=True)
        assert failure is not None
        raise failure

    def _fetch(
        self, url: str, asset: ReleaseAsset, dest: Path, progress: InstallProgress
    ) -> None:
        """Download ``url`` to ``dest`` and check it is exactly the pinned build.

        Errors writing to this machine's disk raise :data:`_LOCAL_FAILURES`
        codes, distinct from the network's, so no other host is tried for them.
        """
        progress.phase = "downloading"
        progress.bytes_done = 0
        digest = hashlib.sha256()
        done = 0
        try:
            out = open(dest, "wb")  # noqa: SIM115 - closed below, errors mapped
        except OSError as exc:
            raise _local_failure(exc) from exc
        try:
            with self._opener(url) as response:
                window_start, window_done = time.monotonic(), 0
                for chunk in _chunks(response):
                    done += len(chunk)
                    if done > asset.size:
                        raise InstallError(
                            "checksum_mismatch",
                            "The download is larger than the pinned build.",
                        )
                    digest.update(chunk)
                    try:
                        out.write(chunk)
                    except OSError as exc:
                        raise _local_failure(exc) from exc
                    progress.bytes_done = done
                    now = time.monotonic()
                    if now - window_start >= _STALL_WINDOW_SECONDS:
                        if done - window_done < _STALL_MIN_BYTES:
                            raise InstallError(
                                "download_failed",
                                f"The download from {url} stalled.",
                            )
                        window_start, window_done = now, done
        except InstallError:
            _close_quietly(out)
            raise
        except (
            OSError,
            urllib.error.URLError,
            http.client.HTTPException,  # e.g. IncompleteRead: the body stopped short
            ValueError,
        ) as exc:
            _close_quietly(out)
            raise InstallError(
                "download_failed", f"Couldn't download {url}: {exc}"
            ) from exc
        try:
            out.close()
        except OSError as exc:
            raise _local_failure(exc) from exc
        progress.phase = "verifying"
        if done != asset.size:
            raise InstallError(
                "download_failed",
                f"The download stopped after {done} of {asset.size} bytes.",
            )
        if digest.hexdigest() != asset.sha256:
            raise InstallError(
                "checksum_mismatch",
                "The download doesn't match the pinned build's SHA-256.",
            )


def _snapshot(progress: InstallProgress) -> InstallProgress:
    return InstallProgress(**asdict(progress))


def _chunks(stream: IO[bytes]) -> Iterator[bytes]:
    # read1 returns whatever one socket read brought; read(n) blocks until n
    # bytes or EOF, so a server sending a byte a minute (inside the socket
    # timeout) would never reach the stall check between chunks.
    read: Callable[[int], bytes] = getattr(stream, "read1", None) or stream.read
    while chunk := read(_CHUNK):
        yield chunk


def _replace(src: Path, dst: Path) -> None:
    """``os.replace``, retried briefly on Windows.

    An antivirus scan of a freshly written executable holds it open for a
    moment, and a rename in that window fails with a sharing violation.
    """
    attempts = 5 if os.name == "nt" else 1
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def _close_quietly(stream: IO[bytes]) -> None:
    try:
        stream.close()
    except OSError:
        pass


def _local_failure(exc: OSError) -> InstallError:
    if exc.errno == errno.ENOSPC:
        return InstallError("no_space", "The disk filled up during the install.")
    return InstallError(
        "write_failed", f"Couldn't write to this computer's disk: {exc}"
    )


def _write_quietly(path: Path, data: dict[str, object]) -> None:
    try:
        path.write_text(json.dumps(data))
    except OSError:
        logger.warning("couldn't record %s", path, exc_info=True)


def _check_free_space(agent_dir: Path, asset: ReleaseAsset, agent: str) -> None:
    """Refuse up front rather than fill the disk halfway through a download."""
    expansion = 1 if asset.archive == "raw" else _ARCHIVE_EXPANSION
    needed = asset.size * expansion + _SPACE_MARGIN
    try:
        free = shutil.disk_usage(agent_dir).free
    except OSError:
        return  # can't tell; the download itself will find out
    if free < needed:
        raise InstallError(
            "no_space",
            f"Installing {agent} needs about {needed >> 20} MB of free disk "
            f"space; this computer has {free >> 20} MB.",
        )


def _check_build_runs(agent: str, binary: Path) -> None:
    """Run the unpacked CLI's ``--version``; raise if it doesn't start."""
    env = {**os.environ, **SELF_UPDATE_OFF.get(agent, {})}
    try:
        result = subprocess.run(
            [str(binary), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_VERSION_CHECK_TIMEOUT,
            env=env,
            check=False,
            # No console window flashing up on Windows.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # A timeout or a file held open (a first-run antivirus scan) may pass
        # next time; a non-zero exit below won't.
        raise InstallError(
            "verify_failed",
            f"The {agent} build doesn't run on this computer: {exc}",
            transient=True,
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-300:]
        raise InstallError(
            "verify_failed",
            f"The {agent} build doesn't run on this computer "
            f"(exit code {result.returncode}){': ' + detail if detail else ''}.",
        )


def _last_activity(path: Path) -> float:
    """The newest mtime in ``path``'s tree (0 when it is already gone)."""
    latest = 0.0
    for entry in [path, *path.rglob("*")]:
        try:
            latest = max(latest, entry.lstat().st_mtime)
        except OSError:
            continue
    return latest


def _sweep_leftovers(agent_dir: Path) -> None:
    """Drop what dead installs left behind.

    Only staging dirs no one has written to for a while: another daemon
    sharing this HOME (one per server, say) may be mid-install in a fresh one.
    Trash dirs are always fair game; their rename already took them out of use.
    """
    cutoff = time.time() - _STALE_STAGING_SECONDS
    for leftover in agent_dir.glob(f"{_STAGING_PREFIX}*"):
        if _last_activity(leftover) < cutoff:
            shutil.rmtree(leftover, ignore_errors=True)
    for trash in agent_dir.glob(f"{_TRASH_PREFIX}*"):
        shutil.rmtree(trash, ignore_errors=True)


def _discard(path: Path) -> bool:
    """Take ``path`` out of use in one rename, then delete it.

    A dir deleted in place can end up half gone (on Windows a running CLI
    keeps its own file), and what's left would still read as an installed
    build. Renamed first, it is either intact or out of the way. Returns False
    when even the rename fails (it is in use); the next start retries.
    """
    trash = path.with_name(f"{_TRASH_PREFIX}{path.name}-{os.getpid()}-{time.time_ns()}")
    try:
        os.replace(path, trash)
    except OSError:
        return False
    shutil.rmtree(trash, ignore_errors=True)
    return True


def _older_versions(agent_dir: Path, pinned: str) -> list[Path]:
    """Build dirs older than ``pinned``. Newer ones are left out: they belong
    to a newer daemon release sharing this HOME."""
    return [
        entry
        for entry in agent_dir.iterdir()
        if entry.is_dir()
        and not entry.name.startswith(".")
        and _version_key(entry.name) < _version_key(pinned)
    ]


def _in_use(build_dir: Path, command_lines: list[str]) -> bool:
    """Whether a running process was started from ``build_dir``: the CLI
    itself (its own path is argv[0]), a sidecar beside it, or a runner the
    daemon handed the path to (``--claude-cli=``, ``--codex-binary=``...)."""
    marks = {f"{build_dir}{os.sep}"}
    try:
        marks.add(f"{build_dir.resolve()}{os.sep}")
    except OSError:
        pass
    return any(mark in line for line in command_lines for mark in marks)


def _running_commands() -> Optional[list[str]]:
    """Every running process's command line; None when they can't be listed.

    Empty on Windows: there a build in use can't be renamed, so `_discard`
    already leaves it alone.
    """
    if os.name == "nt":
        return []
    # By path: a daemon started by a desktop app or service manager can have
    # a PATH without /bin, and "can't list" keeps every old build forever.
    ps = next(
        (path for path in ("/bin/ps", "/usr/bin/ps") if os.path.exists(path)), None
    ) or shutil.which("ps")
    if ps is None:
        return None
    try:
        result = subprocess.run(
            [ps, "-A", "-ww", "-o", "command="],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.splitlines()


def _inside(base: Path, name: str) -> Path:
    target = (base / name).resolve()
    if target != base.resolve() and base.resolve() not in target.parents:
        raise InstallError(
            "unpack_failed", f"The archive tried to write outside its folder: {name}"
        )
    return target


def _unpack(asset: ReleaseAsset, archive: Path, dest: Path) -> None:
    try:
        if asset.archive == "raw":
            target = _inside(dest, asset.binary)
            target.parent.mkdir(parents=True, exist_ok=True)
            _replace(archive, target)
        elif asset.archive == "tar.gz":
            with tarfile.open(archive, "r:gz") as tar:
                members = tar.getmembers()
                has_filter = hasattr(tarfile, "data_filter")
                for member in members:
                    _inside(dest, member.name)
                    if member.isdev():
                        raise InstallError(
                            "unpack_failed",
                            f"The archive holds a device file: {member.name}",
                        )
                    if not (member.issym() or member.islnk()):
                        continue
                    if not has_filter:
                        # Python before 3.11.4 has no "data" filter to police
                        # links as it writes them, and no pinned build has any.
                        raise InstallError(
                            "unpack_failed",
                            f"The archive holds a link, which this Python can't "
                            f"unpack safely: {member.name}",
                        )
                    # A symlink points relative to its own folder; a hard
                    # link names another member, relative to the archive root.
                    _inside(
                        dest,
                        os.path.join(os.path.dirname(member.name), member.linkname)
                        if member.issym()
                        else member.linkname,
                    )
                if has_filter:
                    tar.extractall(dest, filter="data")
                else:
                    tar.extractall(dest)  # noqa: S202 - every member checked above
        elif asset.archive == "zip":
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    target = _inside(dest, info.filename)
                    zf.extract(info, dest)
                    mode = info.external_attr >> 16
                    if mode and os.name != "nt" and not info.is_dir():
                        target.chmod(mode & 0o755)
        else:
            raise InstallError(
                "unpack_failed", f"Unknown archive kind {asset.archive!r}."
            )
    except InstallError:
        raise
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise _local_failure(exc) from exc
        raise InstallError(
            "unpack_failed", f"Couldn't unpack the download: {exc}"
        ) from exc
    except (tarfile.TarError, zipfile.BadZipFile) as exc:
        raise InstallError(
            "unpack_failed", f"Couldn't unpack the download: {exc}"
        ) from exc


# ----- lookup ---------------------------------------------------------------


def _find_managed_copy(
    agent: str,
    *,
    root: Path,
    releases: Mapping[str, PinnedRelease],
    host: Optional[Host],
) -> Optional[ManagedCopy]:
    """The pinned build of ``agent`` under ``root``; failing that, the newest
    build an earlier (or another) daemon release installed, so a daemon upgrade
    never makes a working agent read as missing."""
    release = releases.get(agent)
    if release is None or host is None:
        return None
    asset = release.assets.get(asset_key(agent, host))
    if asset is None:
        return None
    agent_dir = root / agent
    try:
        if not agent_dir.is_dir():
            return None
        older = [
            entry.name
            for entry in agent_dir.iterdir()
            if entry.is_dir()
            and not entry.name.startswith(".")
            and entry.name != release.version
        ]
    except OSError:
        # An unreadable agents dir (one a `sudo` run left root-owned, say)
        # means no copy here. Never an exception: detection runs at daemon
        # start, and the user's own install must still be found.
        return None
    versions = [release.version] + sorted(older, key=_version_key, reverse=True)
    for version in versions:
        candidate = agent_dir / version / asset.binary
        try:
            present = candidate.is_file()
        except OSError:
            continue
        if present:
            return ManagedCopy(
                version=version,
                path=str(candidate),
                pinned=version == release.version,
            )
    return None


def managed_cli_path(agent: str) -> Optional[str]:
    """The installed managed copy of ``agent``'s CLI, or None."""
    copy = _find_managed_copy(
        agent, root=agents_root(), releases=PINNED_RELEASES, host=detect_host()
    )
    return copy.path if copy is not None else None


def has_build_for_this_host() -> bool:
    """Whether any agent this release pins has a build for this machine."""
    host = detect_host()
    return host is not None and any(
        asset_key(agent, host) in release.assets
        for agent, release in PINNED_RELEASES.items()
    )


@functools.lru_cache(maxsize=1)
def sdk_bundles_claude() -> bool:
    """Whether the Claude Agent SDK here carries its own Claude CLI build.

    A pip or npm install of Vicoa gets the SDK's platform wheel, which does;
    the frozen daemon in the desktop app leaves that ~370 MB file out.
    """
    # Located, not imported: importing loads the whole SDK (hundreds of
    # modules, ~30 MB) into the long-lived daemon just to check one file.
    try:
        spec = importlib.util.find_spec("claude_agent_sdk")
    except (ImportError, ValueError):
        return False
    if spec is None or not spec.origin:
        return False
    name = "claude.exe" if sys.platform == "win32" else "claude"
    return (Path(spec.origin).parent / "_bundled" / name).is_file()


def pinned_build_env(agent: str, cli_path: Optional[str]) -> dict[str, str]:
    """Environment that keeps a managed copy on its pinned build.

    Empty for the user's own CLI. Every launcher of a managed copy applies it
    (daemon sessions and the terminal wrappers alike), or the CLI updates
    itself in place to a version this release never ran.
    """
    if agent in SELF_UPDATE_OFF and is_managed_path(cli_path):
        return dict(SELF_UPDATE_OFF[agent])
    return {}


def is_managed_path(path: Optional[str]) -> bool:
    """Whether ``path`` is a CLI Vicoa installed (rather than the user's own)."""
    if not path:
        return False
    base = agents_root().resolve()
    try:
        return base in Path(path).resolve().parents
    except OSError:
        return False


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)
