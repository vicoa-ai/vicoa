#!/usr/bin/env python3
"""Headless Codex Integration for Vicoa via ACP."""

import argparse
import logging
import os
import sys
import uuid
from typing import Any, Dict, Optional

from integrations.headless.acp_base import ACPWrapperBase, ACPWrapperConfig
from vicoa.agents.codex_acp import read_codex_auth_openai_key


logger = logging.getLogger(__name__)


class CodexACPConfig(ACPWrapperConfig):
    """Configuration for Codex ACP integration."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        agent_instance_id: str,
        project_path: str,
        name: str = "Codex",
        is_resuming: bool = False,
        acp_session_id: Optional[str] = None,
        codex_acp_command: str = "codex-acp",
        auth_method: Optional[str] = None,
        codex_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.agent_instance_id = agent_instance_id
        self.project_path = project_path
        self.agent_type = "Codex"
        self.agent_command = codex_acp_command
        self.name = name
        self.is_resuming = is_resuming
        self.acp_session_id = acp_session_id
        self.auth_method = auth_method
        self.codex_api_key = codex_api_key
        self.openai_api_key = openai_api_key
        self.initial_prompt = initial_prompt

    def get_acp_command(self) -> list[str]:
        return [self.agent_command]

    def get_acp_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        if self.codex_api_key:
            env["CODEX_API_KEY"] = self.codex_api_key
        if self.openai_api_key:
            env["OPENAI_API_KEY"] = self.openai_api_key
        return env

    @classmethod
    def from_args(
        cls,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        project_path: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        name: str = "Codex",
        is_resuming: bool = False,
        acp_session_id: Optional[str] = None,
        codex_acp_command: Optional[str] = None,
        auth_method: Optional[str] = None,
        codex_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ) -> "CodexACPConfig":
        final_api_key = api_key or os.environ.get("VICOA_API_KEY")
        if not final_api_key:
            raise ValueError(
                "Vicoa API key required: provide --api-key or set VICOA_API_KEY"
            )

        final_base_url = (
            base_url
            or os.environ.get("VICOA_API_URL")
            or os.environ.get("VICOA_BASE_URL")
            or "https://api.vicoa.ai"
        )
        final_project_path = project_path or os.getcwd()
        final_agent_instance_id = (
            agent_instance_id
            or os.environ.get("VICOA_AGENT_INSTANCE_ID")
            or str(uuid.uuid4())
        )

        final_codex_api_key = codex_api_key or os.environ.get("CODEX_API_KEY")
        final_openai_api_key = (
            openai_api_key
            or os.environ.get("OPENAI_API_KEY")
            or read_codex_auth_openai_key()
        )
        final_auth_method = (
            auth_method
            or os.environ.get("VICOA_CODEX_ACP_AUTH_METHOD")
            or (
                "codex-api-key"
                if final_codex_api_key
                else ("openai-api-key" if final_openai_api_key else "chatgpt")
            )
        )
        final_codex_acp_command = (
            codex_acp_command or os.environ.get("VICOA_CODEX_ACP_PATH") or "codex-acp"
        )

        return cls(
            api_key=final_api_key,
            base_url=final_base_url,
            agent_instance_id=final_agent_instance_id,
            project_path=final_project_path,
            name=name,
            is_resuming=is_resuming,
            acp_session_id=acp_session_id,
            codex_acp_command=final_codex_acp_command,
            auth_method=final_auth_method,
            codex_api_key=final_codex_api_key,
            openai_api_key=final_openai_api_key,
            initial_prompt=initial_prompt,
        )


class CodexACPWrapper(ACPWrapperBase):
    """Headless Codex wrapper using ACP protocol."""

    config: CodexACPConfig

    def build_session_config(self) -> Optional[dict]:
        """Read back the CODEX_* env vars that main() set from CLI flags.

        codex-acp is on the way out — instead of capturing the flags into
        self in main() and threading them through CodexACPConfig, we read
        them back from the environment at register time. This keeps the
        diff small while still surfacing the spawn-time config in the
        chat-header pill (plans/session-config-storage.md §6.3).
        """
        sc = {
            "agent": "codex",
            "model": os.environ.get("CODEX_MODEL"),
            "reasoning_effort": os.environ.get("CODEX_REASONING_EFFORT"),
            "permission_mode": os.environ.get("CODEX_PERMISSION_MODE"),
        }
        return {k: v for k, v in sc.items() if v is not None}

    # codex-acp sessions can be long-running; use a generous timeout.
    _prompt_timeout_seconds: float = 3600.0

    def create_session(self) -> None:
        acp = self.acp
        if not acp:
            raise RuntimeError("ACP client not started")

        auth_payload = {"methodId": self.config.auth_method}
        auth_response = acp.send_request("authenticate", auth_payload, timeout=120.0)
        auth_response.raise_for_error()

        params: Dict[str, Any] = {
            "cwd": self.config.project_path,
            "mcpServers": [],
        }
        response = acp.send_request("session/new", params)
        response.raise_for_error()
        if not response.result:
            raise RuntimeError("session/new response missing result")

        self.session_id = response.result.get("sessionId")
        if not self.session_id:
            raise RuntimeError("session/new response missing sessionId")

        self.log(f"[ACP] Session created: {self.session_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless Codex Integration via ACP")
    parser.add_argument("--api-key", help="Vicoa API key")
    parser.add_argument("--base-url", help="Vicoa base URL")
    parser.add_argument("--project-path", help="Project directory")
    parser.add_argument("--name", default="Codex", help="Agent display name")
    parser.add_argument("--session-id", help="Session ID")
    parser.add_argument(
        "--resume",
        help=(
            "Reattach to an existing Vicoa agent instance by id "
            "(skips registration). This does NOT restore the agent's "
            "conversation -- pass --acp-session-id for that."
        ),
    )
    parser.add_argument(
        "--acp-session-id",
        default=None,
        help=(
            "The agent's own prior session id, restored via ACP "
            "session/load so the conversation continues. Ignored when "
            "the agent does not advertise loadSession."
        ),
    )
    parser.add_argument(
        "--codex-acp-command",
        default=None,
        help="Path to codex-acp binary (defaults to VICOA_CODEX_ACP_PATH or codex-acp)",
    )
    parser.add_argument(
        "--auth-method",
        choices=["chatgpt", "codex-api-key", "openai-api-key"],
        default=None,
        help="codex-acp auth method",
    )
    parser.add_argument("--codex-api-key", help="CODEX_API_KEY override")
    parser.add_argument("--openai-api-key", help="OPENAI_API_KEY override")
    parser.add_argument(
        "--prompt", default=None, help="Initial prompt to send on session start"
    )
    # New flags from plan §5.5 — accepted unconditionally so the daemon's
    # spawn-command line argparses cleanly. Forwarding to codex-acp's
    # underlying codex CLI is best-effort via env vars; the adapter may or
    # may not honor them (plan §11 open question — verify upstream).
    parser.add_argument(
        "--model",
        default=None,
        help="Codex model id; forwarded as env CODEX_MODEL (best-effort).",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["minimal", "low", "medium", "high"],
        help="Codex reasoning effort; forwarded as env CODEX_REASONING_EFFORT.",
    )
    parser.add_argument(
        "--permission-mode",
        default=None,
        choices=["default", "bypassPermissions"],
        help="Codex permission mode; forwarded as env CODEX_PERMISSION_MODE.",
    )
    args = parser.parse_args()
    # Best-effort propagation to codex-acp via env. Set BEFORE constructing
    # the wrapper so its env capture (`get_acp_env`) sees them.
    if args.model:
        os.environ["CODEX_MODEL"] = args.model
    if args.reasoning_effort:
        os.environ["CODEX_REASONING_EFFORT"] = args.reasoning_effort
    if args.permission_mode:
        os.environ["CODEX_PERMISSION_MODE"] = args.permission_mode

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    agent_instance_id = args.resume or args.session_id
    is_resuming = bool(args.resume)
    acp_session_id = args.acp_session_id

    try:
        config = CodexACPConfig.from_args(
            api_key=args.api_key,
            base_url=args.base_url,
            project_path=args.project_path,
            agent_instance_id=agent_instance_id,
            name=args.name,
            is_resuming=is_resuming,
            acp_session_id=acp_session_id,
            codex_acp_command=args.codex_acp_command,
            auth_method=args.auth_method,
            codex_api_key=args.codex_api_key,
            openai_api_key=args.openai_api_key,
            initial_prompt=args.prompt,
        )
        wrapper = CodexACPWrapper(config)
        return wrapper.run()
    except Exception as e:
        logger.error(f"Failed to start Codex ACP wrapper: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
