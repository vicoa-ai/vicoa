#!/usr/bin/env python3
"""Vicoa MCP Server - Stdio Transport

This is the stdio version of the Vicoa MCP server that can be installed via pip/pipx.
It provides the same functionality as the hosted server but uses stdio transport.
"""

import argparse
import asyncio
import logging
from typing import Optional

from fastmcp import FastMCP
from vicoa.sdk import AsyncVicoaClient
from vicoa.sdk.exceptions import TimeoutError as VicoaTimeoutError

from .models import AskQuestionResponse, EndSessionResponse, LogStepResponse
from .descriptions import (
    LOG_STEP_DESCRIPTION,
    ASK_QUESTION_DESCRIPTION,
    END_SESSION_DESCRIPTION,
)
from .utils import detect_agent_type_from_environment


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global client instance
client: Optional[AsyncVicoaClient] = None

# Global state for current agent instance (primarily used for claude code approval tool)
current_agent_instance_id: Optional[str] = None

# Global state for permission tracking (agent_instance_id -> permissions)
# Structure: {agent_instance_id: {"Edit": True, "Write": True, "Bash": {"ls": True, "git": True}}}
permission_state: dict[str, dict] = {}


def get_client() -> AsyncVicoaClient:
    """Get the initialized AsyncVicoaClient instance."""
    if client is None:
        raise RuntimeError("Client not initialized. Run main() first.")
    return client


def format_dict_as_markdown(data: dict) -> str:
    """Format a dictionary as readable markdown.

    Args:
        data: Dictionary to format

    Returns:
        Formatted markdown string
    """
    lines = []
    for key, value in data.items():
        # Bold the key
        lines.append(f"**{key}:**")
        # Format the value based on its type
        if isinstance(value, dict):
            # Recursively format nested dicts with indentation
            nested = format_dict_as_markdown(value)
            indented = "\n".join(f"  {line}" for line in nested.split("\n"))
            lines.append(indented)
        elif isinstance(value, list):
            # Format lists as bullet points
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, str) and "\n" in value:
            # Multi-line strings in code blocks
            lines.append("```")
            lines.append(value)
            lines.append("```")
        else:
            # Simple values inline
            lines.append(f"  {value}")
        lines.append("")  # Empty line between entries
    return "\n".join(lines).rstrip()


# Create FastMCP server and metadata
mcp = FastMCP(
    "Vicoa Agent Dashboard MCP Server",
)


@mcp.tool(name="log_step", description=LOG_STEP_DESCRIPTION)
async def log_step_tool(
    agent_instance_id: str | None = None,
    step_description: str = "",
) -> LogStepResponse:
    global current_agent_instance_id

    agent_type = detect_agent_type_from_environment()
    client = get_client()

    response = await client.send_message(
        agent_type=agent_type,
        content=step_description,
        agent_instance_id=agent_instance_id,
        requires_user_input=False,  # Log steps don't require user input
    )

    if current_agent_instance_id is None:
        current_agent_instance_id = response.agent_instance_id

    # Return LogStepResponse with queued messages as user_feedback
    return LogStepResponse(
        success=response.success,
        agent_instance_id=response.agent_instance_id,
        step_number=1,  # We don't track step numbers anymore
        user_feedback=response.queued_user_messages,
    )


@mcp.tool(
    name="ask_question",
    description=ASK_QUESTION_DESCRIPTION,
)
async def ask_question_tool(
    agent_instance_id: str | None = None,
    question_text: str | None = None,
) -> AskQuestionResponse:
    global current_agent_instance_id

    if not agent_instance_id:
        raise ValueError("agent_instance_id is required")
    if not question_text:
        raise ValueError("question_text is required")

    agent_type = detect_agent_type_from_environment()
    client = get_client()

    if current_agent_instance_id is None:
        current_agent_instance_id = agent_instance_id

    try:
        response = await client.send_message(
            agent_type=agent_type,
            agent_instance_id=agent_instance_id,
            content=question_text,
            requires_user_input=True,  # Questions require user input
            timeout_minutes=1440,  # 24 hours default
            poll_interval=10.0,
        )

        # Get the answer from queued_user_messages
        answer = (
            response.queued_user_messages[0] if response.queued_user_messages else ""
        )

        return AskQuestionResponse(
            answer=answer,
            question_id=response.message_id,
        )
    except VicoaTimeoutError:
        raise TimeoutError("Question timed out waiting for user response")


@mcp.tool(
    name="end_session",
    description=END_SESSION_DESCRIPTION,
)
async def end_session_tool(
    agent_instance_id: str,
) -> EndSessionResponse:
    global current_agent_instance_id

    client = get_client()

    response = await client.end_session(
        agent_instance_id=agent_instance_id,
    )

    current_agent_instance_id = None

    return EndSessionResponse(
        success=response.success,
        agent_instance_id=response.agent_instance_id,
        final_status=response.final_status,
    )


@mcp.tool(
    name="approve",
    description="Handle permission prompts for Claude Code. Returns approval/denial for tool execution. **NEVER USE THIS TOOL**",
)
async def approve_tool(
    tool_name: str,
    input: dict,
    tool_use_id: Optional[str] = None,
) -> dict:
    """Claude Code permission prompt handler."""
    global current_agent_instance_id, permission_state

    if not tool_name:
        raise ValueError("tool_name is required")

    client = get_client()

    # Use existing instance ID or create a new one
    if current_agent_instance_id:
        instance_id = current_agent_instance_id
    else:
        # Only create a new instance if we don't have one
        response = await client.send_message(
            agent_type="Claude Code",
            content="Permission request",
            agent_instance_id=None,
            requires_user_input=False,
        )
        instance_id = response.agent_instance_id
        current_agent_instance_id = instance_id

    # Check if we have cached permissions for this instance
    instance_permissions = permission_state.get(instance_id, {})

    # Check if this tool/command is already approved
    if tool_name == "Bash":
        # For Bash, check command prefix
        command = input.get("command", "")
        if command:
            # Extract the first word (command name)
            command_parts = command.split()
            if command_parts:
                command_prefix = command_parts[0]
                bash_permissions = instance_permissions.get("Bash", {})
                if bash_permissions.get(command_prefix):
                    return {
                        "behavior": "allow",
                        "updatedInput": input,
                    }
    else:
        # Simple tools - just check if approved
        if instance_permissions.get(tool_name):
            return {
                "behavior": "allow",
                "updatedInput": input,
            }

    # Format the permission request based on tool type
    # Define option texts that will be used for comparison
    option_yes = "Yes"
    option_no = "No"

    if tool_name == "Bash":
        command = input.get("command", "")
        command_parts = command.split()
        command_prefix = command_parts[0] if command_parts else "command"
        option_yes_session = f"Yes and approve {command_prefix} for rest of session"

        question_text = f"Allow execution of Bash {command_prefix}?\n\n**Full command:**\n```bash\n{command}\n```\n\n"
        question_text += "[OPTIONS]\n"
        question_text += f"1. {option_yes}\n"
        question_text += f"2. {option_yes_session}\n"
        question_text += f"3. {option_no}\n"
        question_text += "[/OPTIONS]"
    elif tool_name == "AskUserQuestion":
        option_yes_session = f"Yes and approve {tool_name} for rest of session"
        questions = input.get("questions", [])

        question_text = "Allow execution of AskUserQuestion?\n\n"
        for i, q in enumerate(questions, 1):
            if len(questions) > 1:
                header = q.get("header", f"Question {i}")
                question_text += f"**[{header}]** {q.get('question', '')}\n\n"
            else:
                question_text += f"**Question:** {q.get('question', '')}\n\n"

            options = q.get("options", [])
            if options:
                question_text += "**Options:**\n"
                for opt in options:
                    if isinstance(opt, dict):
                        label = opt.get("label", "")
                        description = opt.get("description", "")
                        if description:
                            question_text += f"- **{label}** — {description}\n"
                        else:
                            question_text += f"- **{label}**\n"
                    else:
                        question_text += f"- {opt}\n"
                question_text += "\n"

        question_text += "[OPTIONS]\n"
        question_text += f"1. {option_yes}\n"
        question_text += f"2. {option_yes_session}\n"
        question_text += f"3. {option_no}\n"
        question_text += "[/OPTIONS]"
    else:
        option_yes_session = f"Yes and approve {tool_name} for rest of session"

        # Format the input dict as markdown
        formatted_input = format_dict_as_markdown(input)

        question_text = (
            f"Allow execution of {tool_name}?\n\n**Input:**\n{formatted_input}\n\n"
        )
        question_text += "[OPTIONS]\n"
        question_text += f"1. {option_yes}\n"
        question_text += f"2. {option_yes_session}\n"
        question_text += f"3. {option_no}\n"
        question_text += "[/OPTIONS]"

    try:
        # Ask the permission question
        await asyncio.sleep(
            1
        )  # This prevents a race condition in claude code when a tool call gets logged vs permission gets asked
        response = await client.send_message(
            agent_instance_id=instance_id,
            content=question_text,
            requires_user_input=True,
            timeout_minutes=1440,
            poll_interval=10.0,
        )

        # Parse the answer to determine approval
        # Get the answer from queued_user_messages
        answer = (
            response.queued_user_messages[0].strip()
            if response.queued_user_messages
            else ""
        )

        # Handle option selections by comparing with actual option text
        if answer == option_yes:
            # Yes - allow once
            return {
                "behavior": "allow",
                "updatedInput": input,
            }
        elif answer == option_yes_session:
            # Yes and approve for rest of session
            # Save permission state
            if instance_id not in permission_state:
                permission_state[instance_id] = {}

            if tool_name == "Bash":
                command = input.get("command", "")
                command_parts = command.split()
                if command_parts:
                    command_prefix = command_parts[0]
                    if "Bash" not in permission_state[instance_id]:
                        permission_state[instance_id]["Bash"] = {}
                    permission_state[instance_id]["Bash"][command_prefix] = True
            else:
                permission_state[instance_id][tool_name] = True

            return {
                "behavior": "allow",
                "updatedInput": input,
            }
        elif answer == option_no:
            # No - deny
            return {
                "behavior": "deny",
                "message": "Permission denied by user",
            }
        else:
            # Custom text response - treat as denial with message
            return {
                "behavior": "deny",
                "message": f"Permission denied by user: {answer}",
            }

    except VicoaTimeoutError:
        return {
            "behavior": "deny",
            "message": "Permission request timed out",
        }


def main():
    """Main entry point for the stdio server"""
    parser = argparse.ArgumentParser(description="Vicoa MCP Server (Stdio)")
    parser.add_argument("--api-key", required=True, help="API key for authentication")
    parser.add_argument(
        "--base-url",
        default="https://agents.vicoa.ai",
        help="Base URL of the Vicoa API server",
    )
    parser.add_argument(
        "--permission-tool",
        action="store_true",
        help="Enable Claude Code permission prompt tool for handling tool execution approvals",
    )
    parser.add_argument(
        "--git-diff",
        action="store_true",
        help="(Deprecated, no longer used) Previously enabled git diff capture",
    )
    parser.add_argument(
        "--agent-instance-id",
        type=str,
        help="Pre-existing agent instance ID to use for this session",
    )
    parser.add_argument(
        "--disable-tools",
        action="store_true",
        help="Disable all tools except the permission tool",
    )

    args = parser.parse_args()

    global client, current_agent_instance_id
    client = AsyncVicoaClient(
        api_key=args.api_key,
        base_url=args.base_url,
    )

    if args.agent_instance_id:
        current_agent_instance_id = args.agent_instance_id
        logger.info(f"Using provided agent instance ID: {args.agent_instance_id}")

    # Enable/disable tools based on feature flags
    if not args.permission_tool:
        mcp.local_provider.remove_tool("approve")

    if args.disable_tools:
        # Remove all tools except the permission tool
        mcp.local_provider.remove_tool("log_step")
        mcp.local_provider.remove_tool("ask_question")
        mcp.local_provider.remove_tool("end_session")
        logger.info("All tools disabled except permission tool")

    logger.info("Starting Vicoa MCP server (stdio)")
    logger.info(f"Using API server: {args.base_url}")
    logger.info(
        f"Claude Code permission tool: {'enabled' if args.permission_tool else 'disabled'}"
    )
    logger.info(f"Tools disabled: {args.disable_tools}")

    try:
        # Run with stdio transport (default)
        mcp.run(transport="stdio")
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
        raise
    finally:
        # Clean up client
        if client:
            asyncio.run(client.close())


if __name__ == "__main__":
    main()
