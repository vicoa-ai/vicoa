"""User identity API: the avatar bytes behind ``<PrincipalAvatar>`` (collab P0).

Deliberately the mirror of the project-icon endpoints in :mod:`backend.api.tasks`
— same upload validation, same storage key shape, same served-URL indirection —
because a user and a project are two of the three principals the avatar
component renders, and they should not drift.

Privacy: an avatar is the one piece of identity that shows up on a shared
surface, so nothing here ever returns an email. ``GET /users/{id}/avatar``
answers image bytes or 404, nothing else.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared import avatars, storage
from shared.database.models import User
from shared.database.session import get_db
from shared.images import InvalidImageError, process_image

from ..auth.dependencies import get_current_user
from ..db import user_queries

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])

# Bounds the request body; decode memory is bounded separately by
# shared.images.MAX_PIXELS.
MAX_AVATAR_UPLOAD_BYTES = 8 * 1024 * 1024
# The raster types process_image emits — served inline; anything else is a bug.
_INLINE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class UserAvatarResponse(BaseModel):
    """Just the avatar fields — never the email (see the module docstring)."""

    id: str
    display_name: str | None
    avatar_image_uri: str | None
    avatar_source: str | None
    updated_at: str


def _avatar_response(user: User) -> UserAvatarResponse:
    return UserAvatarResponse(
        id=str(user.id),
        display_name=user.display_name,
        avatar_image_uri=user.avatar_image_uri,
        avatar_source=user.avatar_source,
        updated_at=user.updated_at.isoformat(),
    )


@router.put("/me/avatar", response_model=UserAvatarResponse)
def upload_my_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserAvatarResponse:
    """Set the caller's avatar from an upload. 'user' beats any OAuth re-seed."""
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
            storage.user_avatar_key(str(current_user.id)),
            processed.data,
            processed.mime_type,
        )
    except Exception as exc:
        logger.exception("avatar upload to S3 failed")
        raise HTTPException(status_code=502, detail="Failed to store image") from exc

    updated = user_queries.set_user_avatar(
        db, current_user, avatar_image_uri=avatars.avatar_served_url(current_user.id)
    )
    return _avatar_response(updated)


@router.delete("/me/avatar", response_model=UserAvatarResponse)
def delete_my_avatar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserAvatarResponse:
    """Drop the image and fall back to generated initials."""
    if current_user.avatar_image_uri:
        try:
            storage.delete_object(storage.user_avatar_key(str(current_user.id)))
        except Exception:
            # Orphaned S3 object is harmless; never fail the reset on it.
            logger.warning("avatar S3 delete failed for %s", current_user.id)
    return _avatar_response(user_queries.clear_user_avatar(db, current_user))


@router.get("/users/{user_id}/avatar")
def get_user_avatar(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Serve a user's avatar bytes (uploaded or OAuth-seeded).

    Authenticated but not grant-scoped: an avatar is the least sensitive field a
    principal has, it is exactly what a shared surface is meant to show, and the
    id has to be known already to ask. When ``shared/access.py`` lands (P3) this
    is where a visibility check would go; until then a uniform 404 is the only
    signal, and no email or name is reachable through it.
    """
    user = db.get(User, user_id)
    if user is None or not user.avatar_image_uri:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found"
        )
    try:
        data, content_type = storage.download_object(
            storage.user_avatar_key(str(user_id))
        )
    except Exception as exc:
        logger.exception("avatar download from S3 failed")
        raise HTTPException(status_code=502, detail="Failed to fetch image") from exc
    if content_type not in _INLINE_IMAGE_TYPES:
        content_type = "application/octet-stream"
    return Response(
        content=data,
        media_type=content_type,
        headers={
            # Short-lived: the URL is stable across replacements, so clients
            # cache-bust with the user's updated_at instead of relying on this.
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )
