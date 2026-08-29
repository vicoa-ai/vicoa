"""Local RPC dispatch: daemon methods + pty-* + git-worktree-create.

`rpc-call` frames from the local WebSocket route here. Everything the cloud
daemon already serves (`spawn-session`, files, git, worktrees) delegates
straight into ``MachineDaemon._handle_rpc_request`` — no proxy hop. The
desktop-only additions (`pty-*` for the terminal tab, `git-worktree-create`)
are handled in this module.

Handlers are sync/blocking; the WebSocket layer runs ``dispatch`` in a thread
executor. Failures are returned as ``{"error": ...}`` result dicts — the same
convention the daemon uses — so the renderer sees a normal ``rpc-result``.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from vicoa.terminal.rpc import PTY_RPC_METHODS, handle_pty_rpc
from vicoa.terminal.service import TerminalService

logger = logging.getLogger(__name__)

# Methods this dispatcher serves on top of the daemon's own (mirrors
# MachineDaemon._supported_rpc_methods): git-worktree-create plus the pty-*
# terminal methods (shared with the cloud daemon via vicoa.terminal.rpc).
LOCAL_ONLY_RPC_METHODS: tuple[str, ...] = (
    "git-worktree-create",
    *PTY_RPC_METHODS,
)


class LocalRpcDispatcher:
    """Routes local `rpc-call` methods to the daemon or local handlers."""

    def __init__(
        self,
        *,
        daemon_dispatch: Callable[[dict[str, Any]], dict[str, Any]],
        daemon_methods: list[str],
        terminal: TerminalService,
    ) -> None:
        self._daemon_dispatch = daemon_dispatch
        self._daemon_methods = list(daemon_methods)
        self._terminal = terminal

    def methods(self) -> list[str]:
        return [*self._daemon_methods, *LOCAL_ONLY_RPC_METHODS]

    def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        pty_result = handle_pty_rpc(self._terminal, method, params)
        if pty_result is not None:
            return pty_result
        try:
            if method == "git-worktree-create":
                return self._git_worktree_create(params)
            return self._daemon_dispatch({"method": method, "params": params})
        except (ValueError, RuntimeError) as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - any failure -> rpc result
            logger.exception("local rpc %s failed", method)
            return {"error": f"RPC {method} failed: {exc}"}

    # ------------------------------------------------------------------
    # git-worktree-create
    # ------------------------------------------------------------------
    def _git_worktree_create(self, params: dict[str, Any]) -> dict[str, Any]:
        cwd = params.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            return {"error": "git-worktree-create requires a cwd"}
        branch = params.get("branch")
        explicit_path = params.get("path")

        if not isinstance(branch, str) or not branch.strip():
            # No branch requested: reuse the daemon's generator (unique
            # branch + computed path) exactly as `spawn-session worktree:new`.
            from vicoa.rpc.worktree_ops import create_worktree

            return create_worktree(cwd)

        from vicoa.rpc.worktree_paths import repo_basename, worktrees_parent_dir

        branch_name = branch.strip()
        abs_repo = Path(os.path.expanduser(cwd)).resolve()
        if not (abs_repo / ".git").exists():
            probe = subprocess.run(
                ["git", "-C", str(abs_repo), "rev-parse", "--git-dir"],
                capture_output=True,
                check=False,
            )
            if probe.returncode != 0:
                return {"error": "not_a_repo"}

        if isinstance(explicit_path, str) and explicit_path.strip():
            target = Path(os.path.expanduser(explicit_path.strip())).resolve()
        else:
            parent = worktrees_parent_dir(abs_repo)
            target = parent / branch_name / repo_basename(abs_repo)
        target.parent.mkdir(parents=True, exist_ok=True)

        proc = subprocess.run(
            [
                "git",
                "-C",
                str(abs_repo),
                "worktree",
                "add",
                "-b",
                branch_name,
                str(target),
            ],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            return {
                "error": proc.stderr.decode("utf-8", errors="replace").strip()
                or "worktree_add_failed"
            }
        return {"path": str(target), "branch": branch_name}
