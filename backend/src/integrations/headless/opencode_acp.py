#!/usr/bin/env python3
"""Headless OpenCode Integration for Vicoa via ACP."""

import argparse
import logging
import os
import sys
import uuid
from typing import Optional, Dict, Any

from integrations.headless.acp_base import ACPWrapperBase, ACPWrapperConfig


logger = logging.getLogger(__name__)


class OpenCodeACPConfig(ACPWrapperConfig):
    """Configuration for OpenCode ACP integration."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        agent_instance_id: str,
        project_path: str,
        agent_mode: str = "build",
        opencode_api_key: Optional[str] = None,
        model: Optional[str] = None,
        name: str = "OpenCode",
        is_resuming: bool = False,
        acp_session_id: Optional[str] = None,
        opencode_command: str = "opencode",
        initial_prompt: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.agent_instance_id = agent_instance_id
        self.project_path = project_path
        self.agent_type = "OpenCode"
        self.agent_command = opencode_command

        self.agent_mode = agent_mode
        self.opencode_api_key = opencode_api_key
        self.model = model

        self.name = name
        self.is_resuming = is_resuming
        self.acp_session_id = acp_session_id
        self.initial_prompt = initial_prompt

    def get_acp_command(self) -> list[str]:
        return [self.agent_command, "acp"]

    def get_acp_env(self) -> dict[str, str]:
        env = {}

        if self.opencode_api_key:
            env["ANTHROPIC_API_KEY"] = self.opencode_api_key
            env["OPENCODE_API_KEY"] = self.opencode_api_key

        if self.model:
            env["OPENCODE_MODEL"] = self.model

        env["NODE_ENV"] = "production"

        return env

    @classmethod
    def from_args(
        cls,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        project_path: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        agent_mode: str = "build",
        name: str = "OpenCode",
        is_resuming: bool = False,
        acp_session_id: Optional[str] = None,
        opencode_api_key: Optional[str] = None,
        model: Optional[str] = None,
        opencode_command: str = "opencode",
        initial_prompt: Optional[str] = None,
    ) -> "OpenCodeACPConfig":
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

        if not agent_instance_id:
            agent_instance_id = str(uuid.uuid4())

        final_opencode_api_key = (
            opencode_api_key
            or os.environ.get("OPENCODE_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
        )
        final_model = model or os.environ.get("OPENCODE_MODEL")

        return cls(
            api_key=final_api_key,
            base_url=final_base_url,
            agent_instance_id=agent_instance_id,
            project_path=final_project_path,
            agent_mode=agent_mode,
            name=name,
            is_resuming=is_resuming,
            acp_session_id=acp_session_id,
            opencode_api_key=final_opencode_api_key,
            model=final_model,
            opencode_command=opencode_command,
            initial_prompt=initial_prompt,
        )


class OpenCodeACPWrapper(ACPWrapperBase):
    """Headless OpenCode wrapper using ACP protocol."""

    config: OpenCodeACPConfig

    _prompt_timeout_seconds: float = 1800.0
    _prompt_cancel_grace_period_seconds: float = 15.0
    _hard_interrupt_fallback_delay_seconds: float = 2.0

    def build_session_config(self) -> Optional[dict]:
        """OpenCode tracks model + mode on its config. The mode (build/plan)
        is always present (default 'build'); model is optional."""
        sc = {
            "agent": "opencode",
            "model": self.config.model,
            "opencode_mode": self.config.agent_mode,
        }
        return {k: v for k, v in sc.items() if v is not None}

    def create_session(self) -> None:
        """Create OpenCode coding session via ACP."""
        acp = self.acp
        if not acp:
            from integrations.headless.acp_client import ACPError

            raise ACPError("ACP client not started")

        self.log(f"[ACP] Creating session with mode: {self.config.agent_mode}")

        try:
            from integrations.headless.acp_client import ACPError

            params: Dict[str, Any] = {
                "mode": self.config.agent_mode,
                "cwd": self.config.project_path,
                "mcpServers": [],
            }

            if self.config.model:
                if "/" in self.config.model:
                    provider_id, model_id = self.config.model.split("/", 1)
                    params["model"] = {"providerId": provider_id, "modelId": model_id}

            response = acp.send_request("session/new", params)
            response.raise_for_error()

            if response.result:
                self.session_id = response.result.get("sessionId")
                self.log(f"[ACP] Session created: {self.session_id}")
                # Capture the live model config option so mid-session model
                # switching works (session/set_config_option) and the gear can
                # list OpenCode's provider-aware models.
                self._apply_session_state(response.result)
                self._report_available_models()
                # OpenCode's session/new `model` param isn't reliably honored,
                # so apply the spawn-time model via the live config option (the
                # same set_config_option path the gear uses). No-op for the
                # 'default' sentinel (the daemon doesn't pass --model then).
                self.log(f"[ACP] Spawn model requested: {self.config.model!r}")
                if self.config.model:
                    self._apply_initial_model(self.config.model)
            else:
                raise ACPError("session/new response missing result")

        except Exception as e:
            self.log(f"[ERROR] Failed to create session: {e}")
            raise

    def _handle_late_acp_response(self, request_id: int, response) -> None:
        """Flush final buffered output when a timed-out prompt response arrives late."""
        self.log(
            f"[ACP] Late prompt response for request {request_id}, flushing final output"
        )
        self._awaiting_after_next_agent_output = True
        self._flush_assistant_chunk_buffer()
        self._set_awaiting_input_state()

    def handle_notification(self, method: str, params: Dict[str, Any]) -> None:
        if method == "agent_type":
            self._handle_agent_type_control(params.get("value"))
        elif method == "model":
            self._handle_model_control(params.get("value"))
        elif method in {"permission_mode", "thinking"}:
            self._send_feedback_message(
                f"{method} control is not supported in OpenCode ACP mode."
            )
        else:
            super().handle_notification(method, params)

    def _apply_control_command(self, control: Dict[str, str]) -> None:
        setting = control.get("setting", "")
        value = control.get("value")
        self.log(
            f"[Vicoa] Control command received: {setting}"
            + (f"={value}" if value is not None else "")
        )

        if setting == "interrupt":
            self._handle_interrupt_control()
        elif setting == "agent_type":
            self._handle_agent_type_control(value)
        elif setting == "model":
            self._handle_model_control(value)
        elif setting in {"permission_mode", "thinking"}:
            self._send_feedback_message(
                f"{setting} control is not supported in OpenCode ACP mode."
            )
        else:
            self._send_feedback_message(f"Unknown control setting '{setting}'.")

    def _handle_agent_type_control(self, value: str | None) -> None:
        """Switch OpenCode mode (build/plan)."""
        acp = self.acp
        if not acp or not self.session_id:
            self._send_feedback_message(
                "Failed to change agent mode: session not ready."
            )
            return

        requested_mode = (value or "").strip().lower()
        if requested_mode not in {"build", "plan"}:
            self._send_feedback_message(
                f"Invalid OpenCode mode '{value}'. Valid options: build, plan."
            )
            return

        if requested_mode == self.config.agent_mode:
            self._send_feedback_message(f"Agent mode is already {requested_mode}.")
            return

        method_candidates = ["session/set_mode", "session/setMode"]
        for method in method_candidates:
            try:
                response = acp.send_request(
                    method,
                    {"sessionId": self.session_id, "modeId": requested_mode},
                    timeout=10.0,
                )
                response.raise_for_error()
                self.config.agent_mode = requested_mode
                if self.vicoa_client:
                    self.vicoa_client.patch_agent_instance(
                        self.config.agent_instance_id,
                        session_config={
                            "agent": "opencode",
                            "opencode_mode": requested_mode,
                        },
                    )
                self._send_feedback_message(f"Agent changed to {requested_mode}.")
                return
            except Exception as e:
                self.log(f"[WARNING] Failed {method} for mode {requested_mode}: {e}")
                continue

        self._send_feedback_message(f"Failed to change agent mode to {requested_mode}.")

    def _report_available_models(self) -> None:
        """PATCH OpenCode's live model list + current model onto session_config.

        OpenCode advertises a standard ACP ``model`` config option whose values
        are provider-scoped (e.g. ``opencode/big-pickle``) and reflect only the
        providers the user has configured. Reporting it lets the mid-session
        gear list and switch models live. Mode (build/plan) keeps its own path.
        """
        models = self._live_available_models()
        if not models:
            return
        updates: Dict[str, Any] = {"available_models": models}
        if self.current_model_id:
            updates["current_model"] = self.current_model_id
        self._patch_session_config(updates)

    # OpenCode model switching uses the base live path
    # (session/set_config_option) — see ACPWrapperBase._handle_model_control.
    # Its `model` config option accepts the change immediately; no override.


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Headless OpenCode Integration via ACP"
    )
    parser.add_argument("--api-key", help="Vicoa API key")
    parser.add_argument("--base-url", help="Vicoa base URL")
    parser.add_argument("--project-path", help="Project directory")
    parser.add_argument(
        "--agent-mode",
        default="build",
        choices=["build", "plan"],
        help="OpenCode agent mode",
    )
    parser.add_argument("--name", default="OpenCode", help="Agent display name")
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
    parser.add_argument("--opencode-api-key", help="Anthropic API key for OpenCode")
    parser.add_argument(
        "--model", help="Model override (e.g., 'anthropic/claude-sonnet-4')"
    )
    parser.add_argument(
        "--opencode-command", default="opencode", help="Path to opencode binary"
    )
    parser.add_argument(
        "--prompt", default=None, help="Initial prompt to send on session start"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    agent_instance_id = args.resume or args.session_id
    is_resuming = bool(args.resume)
    acp_session_id = args.acp_session_id

    try:
        config = OpenCodeACPConfig.from_args(
            api_key=args.api_key,
            base_url=args.base_url,
            project_path=args.project_path,
            agent_instance_id=agent_instance_id,
            agent_mode=args.agent_mode,
            name=args.name,
            is_resuming=is_resuming,
            acp_session_id=acp_session_id,
            opencode_api_key=args.opencode_api_key,
            model=args.model,
            opencode_command=args.opencode_command,
            initial_prompt=args.prompt,
        )
        wrapper = OpenCodeACPWrapper(config)
        return wrapper.run()
    except Exception as e:
        logger.error(f"Failed to start OpenCode wrapper: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
