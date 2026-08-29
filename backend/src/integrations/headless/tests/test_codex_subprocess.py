"""Smoke test: spawn a real subprocess and round-trip ``initialize`` over OS
pipes. Catches integration bugs the in-memory fake can't (StreamWriter buffer
flushing, line-buffered stdout, EOF semantics on subprocess exit).

The test runs against ``_fake_codex.py`` (a tiny scripted Python stand-in)
rather than the real ``codex`` binary so it doesn't require a Codex install
or auth in CI. A separate manual smoke against the real binary is the
acceptance gate for Phase 1 in the plan.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from integrations.headless.codex.spawn import spawn_codex_app_server


_FAKE_CODEX = Path(__file__).parent / "_fake_codex.py"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="asyncio subprocess on Windows needs ProactorEventLoop; not in scope",
)
async def test_subprocess_initialize_roundtrip_against_fake_codex():
    spawned = await spawn_codex_app_server(
        command=[sys.executable, str(_FAKE_CODEX)],
    )
    try:
        await spawned.transport.start()
        result = await asyncio.wait_for(
            spawned.transport.send_request(
                "initialize",
                {"clientInfo": {"name": "vicoa"}, "capabilities": {}},
            ),
            timeout=3.0,
        )
        assert result == {"ok": True}
    finally:
        await spawned.aclose()
    # The fake exits 0 after one round-trip; if we ever see non-zero,
    # something blew up inside the stand-in or the transport.
    assert spawned.process.returncode == 0
