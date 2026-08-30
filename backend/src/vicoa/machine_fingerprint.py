"""Derive a stable ``machine_id`` from a per-host hardware identifier so a
machine keeps the same identity across daemon restarts *and* loss of the local
state cache (``~/.vicoa/daemon_state.json``).

Without this the ``machine_id`` is a backend-minted ``uuid4`` whose only anchor
is that cache file: delete it (or let the backend forget the machine) and the
next registration mints a fresh id, so the same physical machine reappears as a
brand-new — and duplicated — entry in the dashboard.

The id is a ``uuid5`` of the OS machine GUID folded together with the API-key
fingerprint. Folding in the key means two users sharing one host derive
distinct ids (``/machines/register`` 403s a machine owned by another user) and
mirrors the existing key-rotation reset in ``machine_identity``. Hostname is
deliberately excluded by default so renaming the machine doesn't churn its
identity; callers that must disambiguate cloned VM images (which share a
hardware GUID) can opt in with ``include_hostname=True``.

Detection is best-effort and platform-specific. When no stable id can be read
(locked-down container, exotic OS) the function returns ``None`` and the caller
falls back to the legacy backend-minted ``uuid4``.

Note: because the id folds in the API key, a re-authentication (new key)
derives a *different* id on cache loss. The authoritative identity anchor is
therefore server-side: the daemon also sends ``hardware_id_hash()`` and the
register endpoint dedups on ``(user_id, hardware_id)``, so re-auth / key
rotation resolve back to the same machine regardless of the derived id.
``compute_stable_machine_id`` is now just the create-time *seed* for that row.
"""

from __future__ import annotations

import hashlib
import platform
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Optional

from vicoa.machine_identity import api_key_fingerprint

# Fixed, deterministic namespace for Vicoa machine ids. Derived from a URL so
# the constant is self-documenting and reproducible rather than an opaque
# literal — never change it or every derived id shifts.
MACHINE_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://vicoa.ai/machine-id")

# Ordered fallbacks for the systemd/D-Bus machine id. Module-level so tests can
# point them at a temp file.
_LINUX_MACHINE_ID_PATHS = ("/etc/machine-id", "/var/lib/dbus/machine-id")


def _macos_platform_uuid() -> Optional[str]:
    """macOS hardware UUID (``IOPlatformUUID``), stable across OS reinstalls."""
    try:
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout)
    return match.group(1) if match else None


def _linux_machine_id() -> Optional[str]:
    """systemd/D-Bus machine id. Regenerated on OS reinstall (new machine)."""
    for path in _LINUX_MACHINE_ID_PATHS:
        try:
            value = Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return None


def _windows_machine_guid() -> Optional[str]:
    """Windows ``MachineGuid`` from the 64-bit Cryptography registry hive.

    Forces the 64-bit view (``KEY_WOW64_64KEY``) so a 32-bit Python build reads
    the same value the OS reports rather than a WOW6432 redirect.
    """
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None
    # Localize the Windows-only API through Any so the type checker on a
    # non-Windows dev/CI host doesn't flag each attribute as unknown.
    reg: Any = winreg
    try:
        with reg.OpenKey(
            reg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            reg.KEY_READ | reg.KEY_WOW64_64KEY,
        ) as key:
            value, _ = reg.QueryValueEx(key, "MachineGuid")
    except OSError:
        return None
    text = str(value).strip()
    return text or None


def detect_hardware_id() -> Optional[str]:
    """Best-effort stable per-host identifier, or ``None`` if none is readable."""
    system = platform.system()
    if system == "Darwin":
        return _macos_platform_uuid()
    if system == "Linux":
        return _linux_machine_id()
    if system == "Windows":
        return _windows_machine_guid()
    return None


def compute_stable_machine_id(
    api_key: str, *, include_hostname: bool = False
) -> Optional[str]:
    """Deterministic ``machine_id`` for this host + API key, or ``None``.

    Returns ``None`` when no stable hardware id is available so the caller can
    fall back to the legacy backend-minted ``uuid4``. Same host + same key
    always yields the same id; a different key (or host) yields a different one.
    """
    hardware_id = detect_hardware_id()
    if not hardware_id:
        return None
    parts = [hardware_id]
    if include_hostname:
        parts.append(platform.node())
    parts.append(api_key_fingerprint(api_key))
    return str(uuid.uuid5(MACHINE_ID_NAMESPACE, "|".join(parts)))


def hardware_id_hash() -> Optional[str]:
    """SHA-256 of the raw hardware id, or ``None`` when none is readable.

    Sent to the backend as ``hardware_id`` so it can dedup a machine on
    ``(user_id, hardware_id)`` — the server-side identity anchor that survives
    re-auth and key rotation. Deliberately folds in NOTHING but the hardware
    id (no API key, no hostname), so the same physical host hashes identically
    for every key and user; the backend scopes it per user. The raw platform
    UUID never leaves the machine — only its SHA-256 does.
    """
    hardware_id = detect_hardware_id()
    if not hardware_id:
        return None
    return hashlib.sha256(hardware_id.encode("utf-8")).hexdigest()
