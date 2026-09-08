#!/usr/bin/env python3
"""Manual acceptance probe for issue #33, against the *real* ``codex app-server``.

The automated tests drive a scripted stand-in. This one drives the real binary
and measures every inbound frame, so "codex never sends anything big enough to
matter" stops being a guess and becomes a number.

    cd backend
    python3 scripts/codex_frame_probe.py                  # with the fix
    python3 scripts/codex_frame_probe.py --reader raw     # what shipped before

``--reader raw`` restores the pre-fix wiring exactly: the transport reading the
child's ``stdout`` directly, capped by asyncio's ``limit`` (64 KiB by default,
i.e. issue #33 as reported; pass ``--raw-limit`` to try the "just raise it"
fix). Run the same workload both ways — the framed run must deliver every
frame; the raw run dies or silently drops one as soon as the workload clears
the cap.

Runs codex with ``approvalPolicy=never`` and a **read-only** sandbox, in a
throwaway directory, and auto-accepts anything it still asks for so the probe
is unattended. It does spend real model tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from integrations.headless.codex.spawn import (  # noqa: E402
    CodexSubprocess,
    spawn_codex_app_server,
)
from integrations.headless.codex.transport import CodexTransport  # noqa: E402
from integrations.headless.jsonl_stream import (  # noqa: E402
    CODEX_MAX_LINE_BYTES,
    STREAM_READ_AHEAD_BYTES,
    JsonlLineReader,
)


_METHOD_RE = re.compile(rb'"method"\s*:\s*"([^"]+)"')
_KIB = 1024
_MIB = 1024 * 1024


class RecordingReader:
    """Pass-through reader that records the size of every physical line."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.frames: List[Tuple[int, str]] = []

    async def readline(self) -> bytes:
        line = await self._inner.readline()
        if line:
            match = _METHOD_RE.search(line[:400])
            method = match.group(1).decode() if match else "<response>"
            self.frames.append((len(line), method))
        return line


async def _build(
    args: argparse.Namespace, cwd: str
) -> Tuple[CodexTransport, RecordingReader, Any]:
    """Wire a transport the way production does, or the way it used to."""
    if args.reader == "framed":
        spawned: CodexSubprocess = await spawn_codex_app_server(cwd=cwd)
        recorder = RecordingReader(spawned.transport._reader)  # noqa: SLF001
        spawned.transport._reader = recorder  # noqa: SLF001
        return spawned.transport, recorder, spawned

    process = await asyncio.create_subprocess_exec(
        "codex",
        "app-server",
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=args.raw_limit,
    )
    assert process.stdout is not None and process.stdin is not None
    recorder = RecordingReader(process.stdout)

    async def drain() -> None:
        assert process.stderr is not None
        while await process.stderr.readline():
            pass

    asyncio.create_task(drain())
    return CodexTransport(reader=recorder, writer=process.stdin), recorder, process


async def _teardown(handle: Any) -> None:
    if isinstance(handle, CodexSubprocess):
        await handle.aclose()
        return
    handle.kill()
    try:
        # A StreamReader that paused its transport (buffer over ``limit``, which
        # is the whole point of ``--reader raw``) can keep ``wait`` from ever
        # seeing EOF. Production bounds this the same way, in
        # ``CodexSubprocess.aclose``.
        await asyncio.wait_for(handle.wait(), timeout=5)
    except asyncio.TimeoutError:
        pass


def _biggest_local_thread() -> Tuple[str, int]:
    """Pick the fattest rollout on this machine — the fattest resume frame."""
    sessions = Path.home() / ".codex" / "sessions"
    rollouts = sorted(
        sessions.rglob("rollout-*.jsonl"), key=lambda p: p.stat().st_size, reverse=True
    )
    if not rollouts:
        sys.exit(
            f"no codex threads under {sessions}; use --thread-id or --workload exec"
        )
    # rollout-<ISO timestamp>-<thread uuid>.jsonl; the uuid is the last 5 groups
    return "-".join(rollouts[0].stem.split("-")[-5:]), rollouts[0].stat().st_size


def _prompt(args: argparse.Namespace, cwd: Path) -> str:
    if args.workload == "custom":
        if not args.prompt:
            sys.exit("--workload custom needs --prompt")
        return args.prompt
    if args.workload == "read":
        blob = cwd / "blob.txt"
        blob.write_text("A" * args.size + "\n")
        return (
            f"Read {blob.name} in this directory in full, then reply with only "
            "the number of characters it contains. Do not summarise it."
        )
    if args.workload == "lines":
        # Same volume, spread over many lines — some truncation logic counts
        # lines rather than bytes, so it is worth trying both shapes.
        rows = max(1, args.size // 75)
        return (
            "Run exactly this command, then reply with only the word DONE. Do "
            "not summarise or comment on the output.\n\n"
            f"  python3 -c \"[print('line %06d ' % i + 'x'*60) for i in range({rows})]\""
        )
    return (
        "Run exactly this command, then reply with only the word DONE. Do not "
        "summarise or comment on the output.\n\n"
        f"  python3 -c \"print('A'*{args.size})\""
    )


def _report(frames: List[Tuple[int, str]], reason: Optional[str]) -> int:
    if not frames:
        print("\nNo frames recorded at all — codex never spoke.")
        return 1
    sizes = sorted(frames, reverse=True)
    total = sum(size for size, _ in frames)
    print(f"\n{'=' * 66}\nframes: {len(frames)}   bytes: {total:,}")
    print(f"largest: {sizes[0][0]:,} bytes  ({sizes[0][1]})")
    print("\ntop 8 frames:")
    for size, method in sizes[:8]:
        print(f"  {size:>12,}  {method}")
    print("\nover threshold:")
    for label, threshold in (
        ("64 KiB (asyncio default)", 64 * _KIB),
        ("1 MiB", _MIB),
        ("2 MiB (a plausible 'just raise the limit')", 2 * _MIB),
        ("64 MiB (CODEX_MAX_LINE_BYTES)", CODEX_MAX_LINE_BYTES),
    ):
        count = sum(1 for size, _ in frames if size > threshold)
        print(f"  > {label}: {count}")
    if reason:
        print(f"\nTRANSPORT DIED: {reason}")
        return 1
    print("\nTransport survived; every frame above was delivered whole.")
    return 0


async def run(args: argparse.Namespace) -> int:
    workdir = Path(tempfile.mkdtemp(prefix="codex-frame-probe-"))
    prompt = "" if args.workload == "resume" else _prompt(args, workdir)
    transport, recorder, handle = await _build(args, str(workdir))

    done = asyncio.Event()
    died: List[str] = []

    async def on_notification(method: str, params: Dict[str, Any]) -> None:
        if method in ("turn/completed", "turn/failed", "error"):
            if method != "turn/completed":
                print(f"  ! {method}: {json.dumps(params)[:300]}")
            done.set()

    def on_close(reason: str) -> None:
        died.append(reason)
        done.set()

    async def approve(params: Dict[str, Any]) -> Dict[str, Any]:
        return {"decision": "accept"}

    async def grant(params: Dict[str, Any]) -> Dict[str, Any]:
        return {"grants": {}, "scope": "turn"}

    async def cancel(params: Dict[str, Any]) -> Dict[str, Any]:
        return {"decision": "cancel"}

    transport.on_notification = on_notification
    transport.on_close = on_close
    transport.register_request_handler("item/commandExecution/requestApproval", approve)
    transport.register_request_handler("item/fileChange/requestApproval", approve)
    transport.register_request_handler("item/permissions/requestApproval", grant)
    transport.register_request_handler("item/tool/requestUserInput", cancel)

    started = time.monotonic()
    try:
        await transport.start()
        await transport.send_request(
            "initialize",
            {
                "clientInfo": {"name": "vicoa-frame-probe", "version": "0"},
                "capabilities": {"experimentalApi": True},
            },
            timeout=30,
        )
        transport.notify("initialized", {})
        if args.workload == "resume":
            thread_id, rollout_bytes = (
                (args.thread_id, 0) if args.thread_id else _biggest_local_thread()
            )
            print(f"cwd:      {workdir}")
            print(f"reader:   {args.reader}", end="")
            print(
                f" (limit {args.raw_limit:,} B)"
                if args.reader == "raw"
                else f" (read-ahead {STREAM_READ_AHEAD_BYTES:,} B, "
                f"ceiling {CODEX_MAX_LINE_BYTES:,} B)"
            )
            print(f"resuming: {thread_id} (rollout {rollout_bytes:,} B on disk)")
            resumed = await transport.send_request(
                "thread/resume",
                {"threadId": thread_id, "cwd": str(workdir)},
                timeout=args.timeout,
            )
            turns = resumed.get("thread", {}).get("turns", [])
            print(f"resumed:  {len(turns)} turns")
            done.set()
        else:
            thread = await transport.send_request(
                "thread/start", {"cwd": str(workdir)}, timeout=60
            )
            params: Dict[str, Any] = {
                "threadId": thread["thread"]["id"],
                "input": [{"type": "text", "text": prompt}],
                "approvalPolicy": "never",
                "sandboxPolicy": {"type": "readOnly"},
            }
            if args.model:
                params["model"] = args.model
            print(f"cwd:      {workdir}")
            print(f"reader:   {args.reader}", end="")
            print(
                f" (limit {args.raw_limit:,} B)"
                if args.reader == "raw"
                else f" (read-ahead {STREAM_READ_AHEAD_BYTES:,} B, "
                f"ceiling {CODEX_MAX_LINE_BYTES:,} B)"
            )
            print(f"prompt:   {prompt.splitlines()[0]}")
            print("waiting for the turn to complete...")
            await transport.send_request("turn/start", params, timeout=120)
        await asyncio.wait_for(done.wait(), timeout=args.timeout)
    except Exception as exc:  # noqa: BLE001 - a probe reports, it doesn't raise
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        if not died:
            died.append(f"{type(exc).__name__}: {exc}")
    finally:
        elapsed = time.monotonic() - started
        await transport.aclose()
        await _teardown(handle)
    print(f"\nturn took {elapsed:.1f}s")
    return _report(recorder.frames, died[0] if died else None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workload",
        choices=("resume", "exec", "lines", "read", "custom"),
        default="resume",
    )
    parser.add_argument(
        "--thread-id",
        help="thread to resume; default is the largest rollout in ~/.codex/sessions",
    )
    parser.add_argument("--size", type=int, default=3_000_000)
    parser.add_argument("--prompt")
    parser.add_argument("--model")
    parser.add_argument("--reader", choices=("framed", "raw"), default="framed")
    parser.add_argument("--raw-limit", type=int, default=64 * _KIB)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    if JsonlLineReader is None:  # pragma: no cover - import sanity
        return 1
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
