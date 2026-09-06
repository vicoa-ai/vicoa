#!/usr/bin/env python3
"""Capture real `omp --mode rpc` wire traces into the .jsonl fixtures here.

Requires an authenticated `omp` on this machine (run `omp`, then `/login`).
Pins a cheap model so a full run costs cents. See README.md for what each
scenario proves and for the sanitization rule.

    python3 capture.py            # rewrite every fixture
    python3 capture.py 03 05      # only scenarios whose name starts with these
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("OMP_TRACE_MODEL", "haiku")

# The real frame carries the operator's private slash-command and skill list, so
# it is replaced with a shape-preserving synthetic set before anything is
# written to disk. Every other frame is archived verbatim.
SAFE_COMMANDS = [
    {
        "name": "model",
        "description": "Switch the active model",
        "source": "builtin",
        "input": {"hint": "<model>"},
    },
    {"name": "compact", "description": "Compact the conversation", "source": "builtin"},
    {
        "name": "security",
        "description": "Run OMP-native security scans",
        "source": "builtin",
        "input": {"hint": "<plan|scan|status>"},
        "subcommands": [
            {"name": "plan", "description": "Create a scan plan"},
            {"name": "scan", "description": "Start a planned scan"},
        ],
    },
    {
        "name": "skill:example-skill",
        "description": "An example bundled skill",
        "source": "skill",
    },
]


def sanitize(frame: dict) -> dict:
    if frame.get("type") == "available_commands_update":
        return {"type": "available_commands_update", "commands": SAFE_COMMANDS}
    return frame


def run(
    name: str,
    *,
    prompt: str,
    argv_extra: tuple[str, ...] = (),
    pre: tuple[dict, ...] = (),
    auto=None,
    wait: float = 120.0,
) -> None:
    """Drive one omp session to `agent_end` and archive its frames."""
    workdir = HERE / "_scratch"
    workdir.mkdir(exist_ok=True)
    (workdir / "sample.txt").write_text("sample content: the quick brown fox\n")

    cmd = ["omp", "--mode", "rpc", "--no-session", "--model", MODEL, *argv_extra]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=workdir,
    )
    frames: list[str] = []
    done = threading.Event()

    def send(payload: dict) -> None:
        try:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
        except Exception:
            pass

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            frames.append(line)
            try:
                frame = json.loads(line)
            except Exception:
                continue
            if auto is not None:
                auto(frame, send)
            if frame.get("type") == "agent_end":
                done.set()

    threading.Thread(target=reader, daemon=True).start()
    send({"type": "negotiate_protocol", "protocolVersion": 2, "id": "neg"})
    time.sleep(1.5)
    for index, frame in enumerate(pre):
        send({**frame, "id": f"pre{index}"})
        time.sleep(0.8)
    send({"type": "prompt", "message": prompt, "id": "p1"})
    done.wait(wait)
    time.sleep(1.5)
    proc.kill()

    out = HERE / f"{name}.jsonl"
    lines = []
    counts: dict[str, int] = {}
    for raw in frames:
        try:
            frame = sanitize(json.loads(raw))
        except Exception:
            continue
        counts[frame.get("type", "?")] = counts.get(frame.get("type", "?"), 0) + 1
        lines.append(json.dumps(frame, separators=(",", ":")))
    out.write_text("\n".join(lines) + "\n")
    print(f"[{name}] {len(lines)} frames -> {out.name}")
    print("   ", json.dumps(counts, sort_keys=True))


def answer_host_tool(frame: dict, send) -> None:
    if frame.get("type") != "host_tool_call":
        return
    send(
        {
            "type": "host_tool_update",
            "id": frame["id"],
            "partialResult": {"content": [{"type": "text", "text": "working..."}]},
        }
    )
    send(
        {
            "type": "host_tool_result",
            "id": frame["id"],
            "result": {
                "content": [
                    {"type": "text", "text": "2 sessions: alpha (running), beta (idle)"}
                ],
                "details": {"sessions": [{"name": "alpha"}, {"name": "beta"}]},
            },
        }
    )


def answer_dialog(frame: dict, send) -> None:
    if frame.get("type") != "extension_ui_request":
        return
    method = frame.get("method")
    if method == "setWidget":
        return
    if method == "select" and frame.get("options"):
        send(
            {
                "type": "extension_ui_response",
                "id": frame["id"],
                "value": frame["options"][0],
            }
        )
    elif method == "input":
        send({"type": "extension_ui_response", "id": frame["id"], "value": "yes"})
    else:
        send({"type": "extension_ui_response", "id": frame["id"], "confirmed": True})


SCENARIOS = {
    "01-text": dict(
        prompt="Reply with exactly the word: hello. Nothing else.", wait=70
    ),
    "02-tools": dict(
        prompt="Use the read tool on ./sample.txt and tell me only the last word of the file.",
        wait=110,
    ),
    "03-hosttool": dict(
        pre=(
            {
                "type": "set_host_tools",
                "tools": [
                    {
                        "name": "vicoa_list_sessions",
                        "label": "List Vicoa sessions",
                        "description": (
                            "List the users Vicoa agent sessions. Call this "
                            "whenever asked about Vicoa sessions."
                        ),
                        "loadMode": "essential",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "limit": {"type": "integer", "description": "max rows"}
                            },
                            "required": [],
                        },
                    }
                ],
            },
        ),
        prompt=(
            "Call the vicoa_list_sessions tool with limit 5, then tell me how "
            "many sessions there are."
        ),
        auto=answer_host_tool,
        wait=110,
    ),
    "04-approval": dict(
        argv_extra=("--approval-mode", "always-ask"),
        prompt=(
            "Create a file named approved.txt in the current directory "
            "containing the word ok. Use the write tool."
        ),
        auto=answer_dialog,
        wait=140,
    ),
    "05-todo": dict(
        prompt=(
            "Make a todo list with exactly three steps for adding a "
            "health-check endpoint to a FastAPI app, then stop without doing them."
        ),
        wait=140,
    ),
    "06-subagent": dict(
        pre=({"type": "set_subagent_subscription", "level": "events"},),
        prompt=(
            "Launch one subagent to count how many lines are in ./sample.txt, "
            "then report the number."
        ),
        wait=200,
    ),
}


def main() -> int:
    wanted = sys.argv[1:]
    for name, kwargs in SCENARIOS.items():
        if wanted and not any(name.startswith(prefix) for prefix in wanted):
            continue
        run(name, **kwargs)  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
