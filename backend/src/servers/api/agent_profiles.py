"""Agent-profile REST for the agent-facing server (collaboration P1).

The human dashboard owns ``/api/v1/agents`` on the ``backend`` process (Supabase
JWT). This module exposes the read + light-write subset to the CLI, which
authenticates against *this* server with its RS256 API-key JWT. Same
servers→backend reuse precedent as ``tasks.py``: the query layer is imported
verbatim from ``backend.db.agent_profile_queries``, so the two surfaces cannot
drift.

Deliberately narrower than the dashboard's: no avatar endpoints. Uploading an
image is not a terminal gesture, and leaving it out keeps this module free of the
storage/Pillow dependency chain.
"""

# NB: no ``from __future__ import annotations`` — it would stringify the
# ``-> None`` on the 204 DELETE, which FastAPI then resolves to ``NoneType``
# (truthy) and rejects as "204 must not have a response body".

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.agent_profiles import (
    AgentProfileCreate,
    AgentProfileResponse,
    AgentProfileUpdate,
    to_response,
)
from backend.db import agent_profile_queries as queries
from shared.agent_catalog import normalize_session_config
from shared.database.session import get_db

from .auth import get_current_user_id

agent_profile_router = APIRouter(tags=["agents"])


def _user_uuid(user_id: str) -> UUID:
    """Coerce the token's ``sub`` (a string) to the UUID the queries expect."""
    try:
        return UUID(user_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id",
        ) from exc


@agent_profile_router.get("/agents", response_model=list[AgentProfileResponse])
def list_agents(
    user_id: Annotated[str, Depends(get_current_user_id)],
    include_archived: bool = False,
    db: Session = Depends(get_db),
) -> list[AgentProfileResponse]:
    return [
        to_response(p)
        for p in queries.list_agent_profiles(
            db, _user_uuid(user_id), include_archived=include_archived
        )
    ]


@agent_profile_router.post(
    "/agents", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED
)
def create_agent(
    payload: AgentProfileCreate,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> AgentProfileResponse:
    uid = _user_uuid(user_id)
    try:
        profile = queries.create_agent_profile(
            db,
            uid,
            name=payload.name,
            description=payload.description,
            color=payload.color,
            emoji=payload.emoji,
            agent=payload.agent,
            config=normalize_session_config(payload.config, payload.agent),
            system_prompt=payload.system_prompt,
            default_machine_id=payload.default_machine_id,
            default_project_id=payload.default_project_id,
            position=queries.next_position(db, uid),
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have an agent named '{payload.name}'",
        ) from exc
    return to_response(profile)


@agent_profile_router.patch("/agents/{profile_id}", response_model=AgentProfileResponse)
def update_agent(
    profile_id: UUID,
    payload: AgentProfileUpdate,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> AgentProfileResponse:
    profile = queries.get_agent_profile(db, _user_uuid(user_id), profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    supplied = payload.model_dump(exclude_unset=True)
    next_agent = supplied.get("agent", profile.agent)
    if "config" in supplied or "agent" in supplied:
        supplied["config"] = normalize_session_config(
            supplied.get("config", profile.config), next_agent
        )
    try:
        return to_response(queries.update_agent_profile(db, profile, supplied))
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have an agent named '{supplied.get('name')}'",
        ) from exc


@agent_profile_router.delete(
    "/agents/{profile_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_agent(
    profile_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> None:
    profile = queries.get_agent_profile(db, _user_uuid(user_id), profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    queries.delete_agent_profile(db, profile)
