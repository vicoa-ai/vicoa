"""Agent profiles API — ``/api/v1/agents`` (collaboration P1).

The user-facing "Agent": a named provider + model + config + instructions with an
avatar. Picked in one click when starting a session, referenced by an automation,
assignable to a task from P2.

The clean ``/agents`` path is free because P0.5 renamed the *agent type* table
internals without touching its legacy ``/user-agents`` route (PR #39) — so the
good name lands on the resource users actually see, and no already-installed
mobile build breaks. See plans/todos/agent-profiles-p1.md §6.

Image endpoints deliberately mirror ``backend/api/users.py`` (the P0 avatar
reference) rather than re-deriving: same upload bound, same ``process_image``
validation, same served-URL indirection, same key-by-id-alone storage shape.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared import storage
from shared.agent_catalog import known_agent_ids, normalize_session_config
from shared.database.agent_profile_models import AgentProfile
from shared.database.models import User
from shared.database.session import get_db
from shared.images import InvalidImageError, process_image

from ..auth.dependencies import get_current_user
from ..db import agent_profile_queries as queries
from ..db.queries import get_agent_profile_instances
from ..models import AgentInstanceResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

# Same bound as user avatars; decode memory is capped separately by
# shared.images.MAX_PIXELS.
MAX_AVATAR_UPLOAD_BYTES = 8 * 1024 * 1024
_INLINE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def avatar_served_url(profile_id: UUID | str) -> str:
    """Backend-relative URL clients render (stored in ``avatar_image_uri``)."""
    return f"/api/v1/agents/{profile_id}/avatar"


def _normalize_agent_id(value: str) -> str:
    """Lowercase + check against the catalog, so a new agent needs no change here."""
    normalized = value.strip().lower()
    known = known_agent_ids()
    if normalized not in known:
        raise ValueError(f"agent must be one of: {', '.join(sorted(known))}")
    return normalized


class AgentProfileResponse(BaseModel):
    id: str
    name: str
    description: str | None
    avatar_image_uri: str | None
    avatar_source: str | None
    color: str | None
    emoji: str | None
    agent: str
    config: dict
    system_prompt: str | None
    default_machine_id: str | None
    default_project_id: str | None
    position: float
    is_archived: bool
    created_at: str
    updated_at: str
    # How many sessions this agent has started, and when any of them was last
    # active (``max(updated_at)``, not the newest start time — see
    # ``session_stats_by_profile``). ``None`` means "not computed": the
    # agent-facing mirror in ``servers/api/agent_profiles.py`` shares this model
    # and the CLI has no use for either number.
    session_count: int | None = None
    last_active_at: str | None = None


class AgentProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    agent: str
    description: str | None = None
    color: str | None = Field(default=None, max_length=16)
    emoji: str | None = Field(default=None, max_length=16)
    config: dict = Field(default_factory=dict)
    system_prompt: str | None = None
    default_machine_id: UUID | None = None
    default_project_id: UUID | None = None

    @field_validator("agent")
    @classmethod
    def validate_agent(cls, value: str) -> str:
        return _normalize_agent_id(value)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class AgentProfileUpdate(BaseModel):
    """All-optional PATCH. ``None`` means "not supplied" — use the model's
    ``model_fields_set`` so an explicit ``null`` can still clear a nullable field."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    agent: str | None = None
    description: str | None = None
    color: str | None = Field(default=None, max_length=16)
    emoji: str | None = Field(default=None, max_length=16)
    config: dict | None = None
    system_prompt: str | None = None
    default_machine_id: UUID | None = None
    default_project_id: UUID | None = None
    position: float | None = None
    is_archived: bool | None = None

    @field_validator("agent")
    @classmethod
    def validate_agent(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_agent_id(value)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class AgentProfileDeleteResponse(BaseModel):
    """The affected-automation count powers the delete confirmation copy: those
    automations keep running off their fallback snapshot (plan §4)."""

    id: str
    automations_affected: int


def to_response(
    profile: AgentProfile,
    *,
    session_count: int | None = None,
    last_active_at: datetime | None = None,
) -> AgentProfileResponse:
    return AgentProfileResponse(
        id=str(profile.id),
        name=profile.name,
        description=profile.description,
        avatar_image_uri=profile.avatar_image_uri,
        avatar_source=profile.avatar_source,
        color=profile.color,
        emoji=profile.emoji,
        agent=profile.agent,
        config=profile.config or {},
        system_prompt=profile.system_prompt,
        default_machine_id=(
            str(profile.default_machine_id) if profile.default_machine_id else None
        ),
        default_project_id=(
            str(profile.default_project_id) if profile.default_project_id else None
        ),
        position=profile.position,
        is_archived=profile.is_archived,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
        session_count=session_count,
        last_active_at=last_active_at.isoformat() if last_active_at else None,
    )


def _with_stats(
    db: Session, user_id: UUID, profile: AgentProfile
) -> AgentProfileResponse:
    """Single-profile response carrying its session count and recency.

    Every endpoint that returns one profile goes through here, so a PATCH
    response can't hand the client a row whose stats are suddenly ``null`` and
    blank them out of the list it just edited.
    """
    count, last = queries.session_stats_by_profile(db, user_id, [profile.id]).get(
        profile.id, (0, None)
    )
    return to_response(profile, session_count=count, last_active_at=last)


def _load_or_404(db: Session, user: User, profile_id: UUID) -> AgentProfile:
    profile = queries.get_agent_profile(db, user.id, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return profile


@router.get("/agents", response_model=list[AgentProfileResponse])
def list_agents(
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AgentProfileResponse]:
    profiles = queries.list_agent_profiles(
        db, current_user.id, include_archived=include_archived
    )
    stats = queries.session_stats_by_profile(
        db, current_user.id, [p.id for p in profiles]
    )
    return [
        to_response(
            p,
            session_count=stats.get(p.id, (0, None))[0],
            last_active_at=stats.get(p.id, (0, None))[1],
        )
        for p in profiles
    ]


@router.post(
    "/agents", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED
)
def create_agent(
    payload: AgentProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentProfileResponse:
    try:
        profile = queries.create_agent_profile(
            db,
            current_user.id,
            name=payload.name,
            description=payload.description,
            color=payload.color,
            emoji=payload.emoji,
            agent=payload.agent,
            config=normalize_session_config(payload.config, payload.agent),
            system_prompt=payload.system_prompt,
            default_machine_id=payload.default_machine_id,
            default_project_id=payload.default_project_id,
            position=queries.next_position(db, current_user.id),
        )
    except IntegrityError as exc:
        db.rollback()
        # The only unique constraint here is (user_id, lower(name)) among
        # non-archived rows.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have an agent named '{payload.name}'",
        ) from exc
    return _with_stats(db, current_user.id, profile)


@router.get("/agents/{profile_id}", response_model=AgentProfileResponse)
def get_agent(
    profile_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentProfileResponse:
    return _with_stats(db, current_user.id, _load_or_404(db, current_user, profile_id))


@router.patch("/agents/{profile_id}", response_model=AgentProfileResponse)
def update_agent(
    profile_id: UUID,
    payload: AgentProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentProfileResponse:
    profile = _load_or_404(db, current_user, profile_id)
    supplied = payload.model_dump(exclude_unset=True)

    # `agent` and `config` move together: the column is authoritative, so a
    # config sent alongside a new agent is re-stamped with it, and changing the
    # agent alone still has to re-stamp the stored blob or the two would disagree.
    next_agent = supplied.get("agent", profile.agent)
    if "config" in supplied or "agent" in supplied:
        supplied["config"] = normalize_session_config(
            supplied.get("config", profile.config), next_agent
        )

    try:
        updated = queries.update_agent_profile(db, profile, supplied)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have an agent named '{supplied.get('name')}'",
        ) from exc
    return _with_stats(db, current_user.id, updated)


@router.delete("/agents/{profile_id}", response_model=AgentProfileDeleteResponse)
def delete_agent(
    profile_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentProfileDeleteResponse:
    profile = _load_or_404(db, current_user, profile_id)
    affected = queries.count_automations_using(db, profile.id)
    if profile.avatar_image_uri:
        try:
            storage.delete_object(storage.agent_profile_avatar_key(str(profile.id)))
        except Exception:
            # An orphaned S3 object is harmless; never fail the delete on it.
            logger.warning("agent avatar S3 delete failed for %s", profile.id)
    queries.delete_agent_profile(db, profile)
    return AgentProfileDeleteResponse(id=str(profile_id), automations_affected=affected)


@router.get("/agents/{profile_id}/sessions", response_model=list[AgentInstanceResponse])
def list_agent_sessions(
    profile_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AgentInstanceResponse]:
    """This agent's run history: the sessions it has started, newest first.

    A sub-resource rather than a filter on ``/agent-instances`` because it is a
    different question — "what has this agent done", not "what am I running" —
    and because ownership of the profile is then checked in exactly one place
    (``_load_or_404``) instead of being a second predicate on the shared list
    query every client already depends on.
    """
    profile = _load_or_404(db, current_user, profile_id)
    return get_agent_profile_instances(db, profile.id, current_user.id, limit=limit)


@router.put("/agents/{profile_id}/avatar", response_model=AgentProfileResponse)
def upload_agent_avatar(
    profile_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentProfileResponse:
    profile = _load_or_404(db, current_user, profile_id)
    raw = file.file.read(MAX_AVATAR_UPLOAD_BYTES + 1)
    if len(raw) > MAX_AVATAR_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds {MAX_AVATAR_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="File is empty")
    try:
        processed = process_image(raw)
    except InvalidImageError as exc:
        raise HTTPException(
            status_code=400, detail="Not a valid image in a supported format"
        ) from exc

    try:
        storage.upload_attachment(
            storage.agent_profile_avatar_key(str(profile.id)),
            processed.data,
            processed.mime_type,
        )
    except Exception as exc:
        logger.exception("agent avatar upload to S3 failed")
        raise HTTPException(status_code=502, detail="Failed to store image") from exc

    return _with_stats(
        db,
        current_user.id,
        queries.set_agent_profile_avatar(
            db, profile, avatar_image_uri=avatar_served_url(profile.id)
        ),
    )


@router.delete("/agents/{profile_id}/avatar", response_model=AgentProfileResponse)
def delete_agent_avatar(
    profile_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentProfileResponse:
    profile = _load_or_404(db, current_user, profile_id)
    if profile.avatar_image_uri:
        try:
            storage.delete_object(storage.agent_profile_avatar_key(str(profile.id)))
        except Exception:
            logger.warning("agent avatar S3 delete failed for %s", profile.id)
    return _with_stats(
        db, current_user.id, queries.clear_agent_profile_avatar(db, profile)
    )


@router.get("/agents/{profile_id}/avatar")
def get_agent_avatar(
    profile_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Serve an agent's avatar bytes.

    Owner-scoped for now: unlike a user avatar (which a shared surface is meant to
    show), an agent profile is not yet reachable by anyone but its owner, so the
    narrower check costs nothing. When ``shared/access.py`` lands (P3) this widens
    to the same visibility rule as the rest of the resource.
    """
    profile = queries.get_agent_profile(db, current_user.id, profile_id)
    if profile is None or not profile.avatar_image_uri:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found"
        )
    try:
        data, content_type = storage.download_object(
            storage.agent_profile_avatar_key(str(profile_id))
        )
    except Exception as exc:
        logger.exception("agent avatar download from S3 failed")
        raise HTTPException(status_code=502, detail="Failed to fetch image") from exc
    if content_type not in _INLINE_IMAGE_TYPES:
        content_type = "application/octet-stream"
    return Response(
        content=data,
        media_type=content_type,
        headers={
            # Short-lived: the URL is stable across replacements, so clients
            # cache-bust on the profile's updated_at instead.
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )
