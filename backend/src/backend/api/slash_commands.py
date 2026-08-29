"""
Slash Commands API endpoints for viewing user's custom commands.

These endpoints allow web and mobile apps to view slash commands
that have been synced from CLI. Commands are read-only from web/mobile;
editing is only supported via CLI.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from shared.database import SlashCommands
from shared.database.session import get_db
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_user
from shared.database.models import User

router = APIRouter(tags=["slash-commands"])


class CommandDetail(BaseModel):
    """Individual command details."""

    name: str = Field(..., description="Command name")
    description: str = Field(..., description="Command description")
    kind: str = Field(
        "command",
        description="'command' or 'skill'. Rows synced before the field "
        "existed default to 'command'.",
    )
    insert: str | None = Field(
        None,
        description="Composer text to insert on selection when it differs "
        "from /name (Codex skills use $name).",
    )


class SlashCommandsResponse(BaseModel):
    """Response model for listing slash commands."""

    agent_type: str = Field(..., description="Agent type (claude, codex, or opencode)")
    commands: List[CommandDetail] = Field(
        default_factory=list, description="List of commands"
    )


@router.get("/commands", response_model=List[SlashCommandsResponse])
def list_slash_commands(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    agent_type: str | None = None,
) -> List[SlashCommandsResponse]:
    """
    Get all slash commands for the current user.

    Query parameters:
    - agent_type: Optional filter for specific agent type ('claude', 'codex', or 'opencode')

    Returns all slash commands synced from CLI, organized by agent type.
    """
    try:
        user_uuid = UUID(str(current_user.id))

        query = db.query(SlashCommands).filter(SlashCommands.user_id == user_uuid)

        if agent_type:
            query = query.filter(SlashCommands.agent_type == agent_type)

        slash_commands_records = query.all()

        result = []
        for record in slash_commands_records:
            commands_list = [
                CommandDetail(
                    name=name,
                    description=details.get("description", ""),
                    kind=details.get("kind", "command"),
                    insert=details.get("insert"),
                )
                for name, details in record.commands.items()
            ]
            result.append(
                SlashCommandsResponse(
                    agent_type=record.agent_type, commands=commands_list
                )
            )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve commands: {str(e)}"
        )


@router.get("/commands/{agent_type}", response_model=SlashCommandsResponse)
def get_commands_for_agent(
    agent_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlashCommandsResponse:
    """
    Get slash commands for a specific agent type.

    Path parameters:
    - agent_type: Agent type ('claude', 'codex', or 'opencode')

    Returns slash commands for the specified agent type.
    """
    try:
        user_uuid = UUID(str(current_user.id))

        slash_commands = (
            db.query(SlashCommands)
            .filter(
                SlashCommands.user_id == user_uuid,
                SlashCommands.agent_type == agent_type,
            )
            .first()
        )

        if not slash_commands:
            return SlashCommandsResponse(agent_type=agent_type, commands=[])

        commands_list = [
            CommandDetail(
                name=name,
                description=details.get("description", ""),
                kind=details.get("kind", "command"),
                insert=details.get("insert"),
            )
            for name, details in slash_commands.commands.items()
        ]

        return SlashCommandsResponse(agent_type=agent_type, commands=commands_list)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve commands: {str(e)}"
        )
