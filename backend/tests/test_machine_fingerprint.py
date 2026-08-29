"""Unit tests for ``vicoa.machine_fingerprint``.

Covers the pure derivation (``compute_stable_machine_id``: determinism,
key-folding, hostname opt-in, fallback) and the per-platform hardware-id
detection (macOS ``ioreg`` parsing, Linux machine-id file read, platform
dispatch).
"""

from __future__ import annotations

import subprocess
import uuid

from vicoa import machine_fingerprint
from vicoa.machine_fingerprint import (
    compute_stable_machine_id,
    detect_hardware_id,
    hardware_id_hash,
)


# ---------------------------------------------------------------------------
# compute_stable_machine_id
# ---------------------------------------------------------------------------


def test_stable_id_is_deterministic(monkeypatch):
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-1")
    first = compute_stable_machine_id("sk-abc")
    second = compute_stable_machine_id("sk-abc")
    assert first == second
    assert first is not None


def test_stable_id_folds_in_api_key(monkeypatch):
    """Two users (keys) on one host must derive distinct ids so the register
    endpoint's per-user ownership check never 403s the second user."""
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-1")
    assert compute_stable_machine_id("sk-a") != compute_stable_machine_id("sk-b")


def test_stable_id_folds_in_hardware(monkeypatch):
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-1")
    one = compute_stable_machine_id("sk-abc")
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-2")
    two = compute_stable_machine_id("sk-abc")
    assert one != two


def test_stable_id_is_a_uuid5(monkeypatch):
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-1")
    parsed = uuid.UUID(compute_stable_machine_id("sk-abc"))
    assert parsed.version == 5


def test_stable_id_none_when_no_hardware_id(monkeypatch):
    """No detectable hardware id → None so the caller keeps the legacy
    backend-minted uuid4 path."""
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: None)
    assert compute_stable_machine_id("sk-abc") is None


def test_hostname_opt_in_changes_and_stays_stable(monkeypatch):
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-1")
    monkeypatch.setattr(machine_fingerprint.platform, "node", lambda: "host-a")
    without = compute_stable_machine_id("sk-abc")
    with_host = compute_stable_machine_id("sk-abc", include_hostname=True)
    assert without != with_host
    # Stable for the same hostname.
    assert with_host == compute_stable_machine_id("sk-abc", include_hostname=True)
    # Changes when the hostname changes.
    monkeypatch.setattr(machine_fingerprint.platform, "node", lambda: "host-b")
    assert with_host != compute_stable_machine_id("sk-abc", include_hostname=True)


# ---------------------------------------------------------------------------
# hardware_id_hash — the stable per-host token sent to the backend for
# server-side (user_id, hardware_id) dedup. Pure hardware, NO api key folded
# in, so the same physical machine hashes the same across key rotation / users.
# ---------------------------------------------------------------------------


def test_hardware_id_hash_is_deterministic(monkeypatch):
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-1")
    assert hardware_id_hash() == hardware_id_hash()
    assert hardware_id_hash() is not None


def test_hardware_id_hash_is_sha256_hex_of_hardware_id(monkeypatch):
    import hashlib

    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-1")
    assert hardware_id_hash() == hashlib.sha256(b"HW-1").hexdigest()


def test_hardware_id_hash_does_not_fold_in_api_key(monkeypatch):
    """Unlike compute_stable_machine_id, the hash is pure hardware so a re-auth
    (new key) yields the SAME hardware_id — the backend dedups on it."""
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-1")
    # No api_key argument at all; value depends only on the hardware id.
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-2")
    other = hardware_id_hash()
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: "HW-1")
    assert hardware_id_hash() != other


def test_hardware_id_hash_none_when_no_hardware_id(monkeypatch):
    monkeypatch.setattr(machine_fingerprint, "detect_hardware_id", lambda: None)
    assert hardware_id_hash() is None


# ---------------------------------------------------------------------------
# detect_hardware_id — platform dispatch
# ---------------------------------------------------------------------------


def test_detect_dispatches_to_macos(monkeypatch):
    monkeypatch.setattr(machine_fingerprint.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(machine_fingerprint, "_macos_platform_uuid", lambda: "MAC-UUID")
    assert detect_hardware_id() == "MAC-UUID"


def test_detect_dispatches_to_linux(monkeypatch):
    monkeypatch.setattr(machine_fingerprint.platform, "system", lambda: "Linux")
    monkeypatch.setattr(machine_fingerprint, "_linux_machine_id", lambda: "LNX-ID")
    assert detect_hardware_id() == "LNX-ID"


def test_detect_dispatches_to_windows(monkeypatch):
    monkeypatch.setattr(machine_fingerprint.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        machine_fingerprint, "_windows_machine_guid", lambda: "WIN-GUID"
    )
    assert detect_hardware_id() == "WIN-GUID"


def test_detect_unknown_platform_is_none(monkeypatch):
    monkeypatch.setattr(machine_fingerprint.platform, "system", lambda: "Plan9")
    assert detect_hardware_id() is None


# ---------------------------------------------------------------------------
# macOS ioreg parsing
# ---------------------------------------------------------------------------


_IOREG_SAMPLE = """
+-o IOPlatformExpertDevice  <class IOPlatformExpertDevice, id 0x100000110>
    "IOPlatformUUID" = "12345678-9ABC-DEF0-1234-56789ABCDEF0"
    "IOPlatformSerialNumber" = "C02XYZ"
"""


def test_macos_uuid_parses_ioreg(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout, check):
        assert cmd[0] == "ioreg"
        return subprocess.CompletedProcess(cmd, 0, stdout=_IOREG_SAMPLE, stderr="")

    monkeypatch.setattr(machine_fingerprint.subprocess, "run", fake_run)
    assert (
        machine_fingerprint._macos_platform_uuid()
        == "12345678-9ABC-DEF0-1234-56789ABCDEF0"
    )


def test_macos_uuid_none_when_ioreg_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("ioreg")

    monkeypatch.setattr(machine_fingerprint.subprocess, "run", fake_run)
    assert machine_fingerprint._macos_platform_uuid() is None


def test_macos_uuid_none_when_not_in_output(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(cmd, 0, stdout="no uuid here", stderr="")

    monkeypatch.setattr(machine_fingerprint.subprocess, "run", fake_run)
    assert machine_fingerprint._macos_platform_uuid() is None


# ---------------------------------------------------------------------------
# Linux machine-id file read
# ---------------------------------------------------------------------------


def test_linux_machine_id_reads_first_present(monkeypatch, tmp_path):
    present = tmp_path / "machine-id"
    present.write_text("abc123def456\n", encoding="utf-8")
    missing = tmp_path / "absent"
    monkeypatch.setattr(
        machine_fingerprint,
        "_LINUX_MACHINE_ID_PATHS",
        (str(missing), str(present)),
    )
    assert machine_fingerprint._linux_machine_id() == "abc123def456"


def test_linux_machine_id_none_when_all_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(
        machine_fingerprint,
        "_LINUX_MACHINE_ID_PATHS",
        (str(tmp_path / "nope1"), str(tmp_path / "nope2")),
    )
    assert machine_fingerprint._linux_machine_id() is None
