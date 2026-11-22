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
"""

from __future__ import annotations

import functools
import hashlib
import http.client
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO, Literal, Optional

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

Phase = Literal["downloading", "verifying", "unpacking", "installed", "failed"]
ErrorCode = Literal[
    "unknown_agent",
    "unsupported_platform",
    "download_failed",
    "checksum_mismatch",
    "unpack_failed",
]


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
    return any(Path("/lib").glob("ld-musl-*.so.1")) or any(
        Path("/lib").glob("libc.musl-*.so.1")
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
    if sys.platform == "darwin":
        os_name: Literal["darwin", "linux", "windows"] = "darwin"
    elif sys.platform.startswith("linux"):
        os_name = "linux"
    elif sys.platform == "win32":
        os_name = "windows"
    else:
        return None

    machine = platform.machine().lower()
    if os_name == "windows":
        # An x64 Python on Windows on ARM reports AMD64; the OS knows better.
        native = (
            os.environ.get("PROCESSOR_ARCHITEW6432")
            or os.environ.get("PROCESSOR_ARCHITECTURE")
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

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message


Opener = Callable[[str], AbstractContextManager[IO[bytes]]]


def _urlopen(url: str) -> AbstractContextManager[IO[bytes]]:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    return urllib.request.urlopen(request, timeout=60)  # noqa: S310 - pinned https URLs


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
        on_installed: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._root = root
        self._releases = releases if releases is not None else PINNED_RELEASES
        self._host = host
        self._opener: Opener = opener or _urlopen
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
        """What installing ``agent`` here means (version, download size), or None."""
        try:
            release, asset = self._resolve(agent)
        except InstallError:
            return None
        return {"version": release.version, "size": asset.size}

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
        progress = running.progress
        try:
            try:
                path = self._install(release, asset, progress)
                progress.path = str(path)
                progress.phase = "installed"
            except InstallError as exc:
                progress.phase, progress.error_code, progress.error = (
                    "failed",
                    exc.code,
                    exc.message,
                )
            except Exception as exc:  # noqa: BLE001 - surface anything as a failed install
                logger.exception("installing %s failed", release.agent)
                progress.phase, progress.error_code = "failed", "download_failed"
                progress.error = f"Couldn't install {release.agent}: {exc}"
            # Published before the install reads as done, so whoever waits on
            # it sees the machine's agents already updated.
            if progress.phase == "installed" and self._on_installed is not None:
                try:
                    self._on_installed(release.agent)
                except Exception:  # noqa: BLE001 - the install itself succeeded
                    logger.warning(
                        "post-install hook for %s failed",
                        release.agent,
                        exc_info=True,
                    )
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
        _sweep_staging(agent_dir)

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
            try:
                os.replace(content, final)
            except OSError:
                # Another daemon finished the same version first: theirs stands.
                if not (final / asset.binary).is_file():
                    raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        _remove_other_versions(agent_dir, keep=release.version)
        return final / asset.binary

    def _download(
        self, asset: ReleaseAsset, dest: Path, progress: InstallProgress
    ) -> None:
        urls = [asset.url] + ([asset.fallback_url] if asset.fallback_url else [])
        failure: Optional[InstallError] = None
        for url in urls:
            try:
                progress.phase = "downloading"
                progress.bytes_done = 0
                digest = hashlib.sha256()
                done = 0
                with self._opener(url) as response, open(dest, "wb") as out:
                    for chunk in _chunks(response):
                        done += len(chunk)
                        if done > asset.size:
                            raise InstallError(
                                "checksum_mismatch",
                                "The download is larger than the pinned build.",
                            )
                        digest.update(chunk)
                        out.write(chunk)
                        progress.bytes_done = done
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
                return
            except InstallError as exc:
                failure = exc
            except (
                OSError,
                urllib.error.URLError,
                http.client.HTTPException,  # e.g. IncompleteRead: the body stopped short
                ValueError,
            ) as exc:
                failure = InstallError(
                    "download_failed", f"Couldn't download {url}: {exc}"
                )
            dest.unlink(missing_ok=True)
        assert failure is not None
        raise failure


def _snapshot(progress: InstallProgress) -> InstallProgress:
    return InstallProgress(**asdict(progress))


def _chunks(stream: IO[bytes]) -> Iterator[bytes]:
    while chunk := stream.read(_CHUNK):
        yield chunk


def _sweep_staging(agent_dir: Path) -> None:
    """Drop what an interrupted install left behind."""
    for leftover in agent_dir.glob(f"{_STAGING_PREFIX}*"):
        shutil.rmtree(leftover, ignore_errors=True)


def _remove_other_versions(agent_dir: Path, keep: str) -> None:
    """Free the space of builds an earlier daemon release installed."""
    for entry in agent_dir.iterdir():
        if entry.is_dir() and entry.name != keep and not entry.name.startswith("."):
            shutil.rmtree(entry, ignore_errors=True)


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
            os.replace(archive, target)
        elif asset.archive == "tar.gz":
            with tarfile.open(archive, "r:gz") as tar:
                for member in tar.getmembers():
                    _inside(dest, member.name)
                    if member.issym() or member.islnk():
                        _inside(
                            dest,
                            os.path.join(os.path.dirname(member.name), member.linkname),
                        )
                    if member.isdev():
                        raise InstallError(
                            "unpack_failed",
                            f"The archive holds a device file: {member.name}",
                        )
                if hasattr(tarfile, "data_filter"):
                    tar.extractall(dest, filter="data")
                else:  # Python before 3.11.4: the checks above are the guard
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
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise InstallError(
            "unpack_failed", f"Couldn't unpack the download: {exc}"
        ) from exc


# ----- lookup ---------------------------------------------------------------


def managed_cli_path(agent: str, root: Optional[Path] = None) -> Optional[str]:
    """The installed managed copy of ``agent``'s CLI, or None.

    The pinned version first; failing that, a build an earlier daemon release
    installed, so an upgrade never makes a working agent read as missing.
    """
    release = PINNED_RELEASES.get(agent)
    host = detect_host()
    if release is None or host is None:
        return None
    asset = release.assets.get(asset_key(agent, host))
    if asset is None:
        return None
    agent_dir = (root or agents_root()) / agent
    if not agent_dir.is_dir():
        return None
    versions = [release.version] + sorted(
        (
            entry.name
            for entry in agent_dir.iterdir()
            if entry.is_dir()
            and not entry.name.startswith(".")
            and entry.name != release.version
        ),
        key=_version_key,
        reverse=True,
    )
    for version in versions:
        candidate = agent_dir / version / asset.binary
        if candidate.is_file():
            return str(candidate)
    return None


def is_managed_path(path: Optional[str], root: Optional[Path] = None) -> bool:
    """Whether ``path`` is a CLI Vicoa installed (rather than the user's own)."""
    if not path:
        return False
    base = (root or agents_root()).resolve()
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
