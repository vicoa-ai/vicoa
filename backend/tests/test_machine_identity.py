"""Unit tests for ``vicoa.machine_identity``.

Covers the pure helpers (``api_key_fingerprint``), the heartbeat-based
ownership probe (``verify_machine_ownership``), and the full decision
function (``decide_identity_action``) across all four state-file
configurations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import requests

from vicoa import machine_identity
from vicoa.machine_identity import (
    IdentityAction,
    api_key_fingerprint,
    decide_identity_action,
    verify_machine_ownership,
)
from vicoa.machine_state import read_daemon_entry, write_daemon_entry


# ---------------------------------------------------------------------------
# api_key_fingerprint
# ---------------------------------------------------------------------------


def test_api_key_fingerprint_is_deterministic():
    assert api_key_fingerprint("sk-xyz-123") == api_key_fingerprint("sk-xyz-123")


def test_api_key_fingerprint_distinguishes_keys():
    assert api_key_fingerprint("sk-a") != api_key_fingerprint("sk-b")


def test_api_key_fingerprint_is_sha256_hex():
    digest = api_key_fingerprint("hello")
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


# ---------------------------------------------------------------------------
# verify_machine_ownership
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_verify_machine_ownership_true_on_200(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(200)

    monkeypatch.setattr(machine_identity.requests, "post", fake_post)

    owned = verify_machine_ownership("sk-good", "https://api.vicoa.ai", "machine-1")

    assert owned is True
    assert captured["url"] == "https://api.vicoa.ai/api/v1/machines/machine-1/heartbeat"
    # Authorization header must carry the current key, not a stale one.
    assert captured["headers"] == {  # type: ignore[comparison-overlap]
        "Authorization": "Bearer sk-good",
        "Content-Type": "application/json",
    }
    # Timeout must be short — this is on the CLI startup path.
    assert captured["timeout"] == 5


def test_verify_machine_ownership_false_on_4xx(monkeypatch):
    monkeypatch.setattr(
        machine_identity.requests, "post", lambda *_a, **_kw: _FakeResponse(403)
    )
    assert (
        verify_machine_ownership("sk-x", "https://api.vicoa.ai", "machine-1") is False
    )


def test_verify_machine_ownership_false_on_404(monkeypatch):
    monkeypatch.setattr(
        machine_identity.requests, "post", lambda *_a, **_kw: _FakeResponse(404)
    )
    assert (
        verify_machine_ownership("sk-x", "https://api.vicoa.ai", "machine-1") is False
    )


def test_verify_machine_ownership_none_on_network_failure(monkeypatch):
    def fake_post(*_args, **_kwargs):
        raise requests.exceptions.ConnectionError("nope")

    monkeypatch.setattr(machine_identity.requests, "post", fake_post)
    # Returning None — caller treats this as "safe-degrade, retry next run".
    assert verify_machine_ownership("sk-x", "https://api.vicoa.ai", "machine-1") is None


def test_verify_machine_ownership_strips_trailing_slash(monkeypatch):
    captured: dict[str, str] = {}

    def fake_post(url, **_kw):
        captured["url"] = url
        return _FakeResponse(200)

    monkeypatch.setattr(machine_identity.requests, "post", fake_post)
    verify_machine_ownership("sk-x", "https://api.vicoa.ai/", "machine-1")
    assert captured["url"] == "https://api.vicoa.ai/api/v1/machines/machine-1/heartbeat"


# ---------------------------------------------------------------------------
# decide_identity_action
# ---------------------------------------------------------------------------


def _no_backend_calls_allowed(*_args, **_kwargs):
    raise AssertionError(
        "decide_identity_action must not hit the backend on the fingerprinted path"
    )


def _state(tmp_path: Path) -> Path:
    return tmp_path / "daemon_state.json"


def test_decide_returns_none_when_fingerprint_matches(monkeypatch, tmp_path):
    sp = _state(tmp_path)
    key = "sk-same-user"
    write_daemon_entry(
        "https://api.vicoa.ai",
        {"machine_id": "m-1", "api_key_fingerprint": api_key_fingerprint(key)},
        sp,
    )
    # If anything reaches the backend on the matching-fp path it's a bug.
    monkeypatch.setattr(
        machine_identity, "verify_machine_ownership", _no_backend_calls_allowed
    )

    assert (
        decide_identity_action(key, "https://api.vicoa.ai", sp) is IdentityAction.NONE
    )
    # State must be left intact.
    assert read_daemon_entry("https://api.vicoa.ai", sp).get("machine_id") == "m-1"


def test_decide_returns_reset_when_fingerprint_differs(monkeypatch, tmp_path):
    sp = _state(tmp_path)
    write_daemon_entry(
        "https://api.vicoa.ai",
        {
            "machine_id": "m-1",
            "api_key_fingerprint": api_key_fingerprint("sk-user-A"),
        },
        sp,
    )
    # Mismatched-fp path must also not need the backend; the decision is local.
    monkeypatch.setattr(
        machine_identity, "verify_machine_ownership", _no_backend_calls_allowed
    )

    assert (
        decide_identity_action("sk-user-B", "https://api.vicoa.ai", sp)
        is IdentityAction.RESET
    )


def test_decide_returns_none_when_state_is_empty(monkeypatch, tmp_path):
    sp = _state(tmp_path)
    # No state file at all → nothing to verify; first run handles it later.
    monkeypatch.setattr(
        machine_identity, "verify_machine_ownership", _no_backend_calls_allowed
    )

    assert (
        decide_identity_action("sk-anything", "https://api.vicoa.ai", sp)
        is IdentityAction.NONE
    )


def test_decide_returns_none_when_no_machine_id_no_fp(monkeypatch, tmp_path):
    sp = _state(tmp_path)
    # Daemon was stopped but its pid was cleared without a machine_id ever
    # being written. Nothing identifying to compare against.
    write_daemon_entry("https://api.vicoa.ai", {"daemon_pid": 999}, sp)
    monkeypatch.setattr(
        machine_identity, "verify_machine_ownership", _no_backend_calls_allowed
    )

    assert (
        decide_identity_action("sk-anything", "https://api.vicoa.ai", sp)
        is IdentityAction.NONE
    )


def test_decide_legacy_state_stamps_fingerprint_when_owned(monkeypatch, tmp_path):
    """Pre-fingerprint upgrade path: state has a machine_id but no fp."""
    sp = _state(tmp_path)
    write_daemon_entry(
        "https://api.vicoa.ai",
        {"machine_id": "m-legacy", "daemon_pid": 4242},
        sp,
    )

    calls: list[tuple[str, str, str]] = []

    def fake_verify(api_key: str, base_url: str, machine_id: str) -> Optional[bool]:
        calls.append((api_key, base_url, machine_id))
        return True

    monkeypatch.setattr(machine_identity, "verify_machine_ownership", fake_verify)

    assert (
        decide_identity_action("sk-current", "https://api.vicoa.ai", sp)
        is IdentityAction.STAMP_FINGERPRINT
    )
    # Verified with the CURRENT key against the persisted machine_id.
    assert calls == [("sk-current", "https://api.vicoa.ai", "m-legacy")]


def test_decide_legacy_state_resets_when_not_owned(monkeypatch, tmp_path):
    sp = _state(tmp_path)
    write_daemon_entry(
        "https://api.vicoa.ai",
        {"machine_id": "m-legacy", "daemon_pid": 4242},
        sp,
    )
    monkeypatch.setattr(
        machine_identity,
        "verify_machine_ownership",
        lambda *_a, **_kw: False,
    )

    assert (
        decide_identity_action("sk-other-user", "https://api.vicoa.ai", sp)
        is IdentityAction.RESET
    )


def test_decide_legacy_state_returns_none_on_network_failure(monkeypatch, tmp_path):
    """Safe-degrade: can't verify → leave state alone, retry next run."""
    sp = _state(tmp_path)
    write_daemon_entry(
        "https://api.vicoa.ai",
        {"machine_id": "m-legacy", "daemon_pid": 4242},
        sp,
    )
    monkeypatch.setattr(
        machine_identity,
        "verify_machine_ownership",
        lambda *_a, **_kw: None,
    )

    assert (
        decide_identity_action("sk-current", "https://api.vicoa.ai", sp)
        is IdentityAction.NONE
    )
    # State must NOT have been modified (no fp stamp, machine_id preserved).
    entry = read_daemon_entry("https://api.vicoa.ai", sp)
    assert "api_key_fingerprint" not in entry
    assert entry.get("machine_id") == "m-legacy"


def test_decide_scoped_by_base_url(monkeypatch, tmp_path):
    """A mismatch under one base_url must not trigger reset under another."""
    sp = _state(tmp_path)
    key_prod = "sk-prod"
    key_staging = "sk-staging"
    write_daemon_entry(
        "https://api.vicoa.ai",
        {"machine_id": "m-prod", "api_key_fingerprint": api_key_fingerprint(key_prod)},
        sp,
    )
    write_daemon_entry(
        "https://staging.vicoa.ai",
        {
            "machine_id": "m-staging",
            "api_key_fingerprint": api_key_fingerprint(key_staging),
        },
        sp,
    )
    monkeypatch.setattr(
        machine_identity, "verify_machine_ownership", _no_backend_calls_allowed
    )

    # Wrong key for prod → RESET; correct key for staging in same file → NONE.
    assert (
        decide_identity_action(key_staging, "https://api.vicoa.ai", sp)
        is IdentityAction.RESET
    )
    assert (
        decide_identity_action(key_staging, "https://staging.vicoa.ai", sp)
        is IdentityAction.NONE
    )
