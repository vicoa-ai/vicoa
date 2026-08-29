"""Attachment endpoints for the app/web chat (Supabase auth).

Upload happens before message send: the client POSTs each picked file (image
or otherwise), gets back an attachment id, then includes the ids in the
message request (see agents.create_user_message_endpoint). Images are
normalized (EXIF stripped, downscaled, re-encoded); any other file type is
stored verbatim. Bytes live in S3; this process proxies them so the client
only ever needs its normal bearer token.
"""

import logging
import mimetypes
import os
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from shared import storage
from shared.database.models import User
from shared.database.session import get_db
from shared.images import InvalidImageError, process_image

from ..auth.dependencies import get_current_user
from ..db import create_attachment, get_attachment_for_user
from ..models import AttachmentResponse

logger = logging.getLogger(__name__)

# Bounds the request body only. Decode memory for images is bounded separately
# by shared.images.MAX_PIXELS — a 113KB PNG can expand into a 108MB bitmap, so
# this cap says nothing about how much memory an image upload will cost. Sized
# so a file base64-encodes below Anthropic's 32MB per-request limit when it is
# delivered inline to Claude (see integrations delivery code).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Executables and OS installers: heavy binaries an agent can't meaningfully
# read, and the sort of payload we don't want to host or hand to a workspace.
# Everything else is allowed — the coding agent decides what to do with it.
_BLOCKED_EXTENSIONS = {
    "exe",
    "msi",
    "dmg",
    "pkg",
    "app",
    "deb",
    "rpm",
    "apk",
    "dll",
    "so",
    "dylib",
    "jar",
    "com",
    "scr",
}
_BLOCKED_MIME_TYPES = {
    "application/x-msdownload",
    "application/x-msdos-program",
    "application/x-dosexec",
    "application/vnd.microsoft.portable-executable",
    "application/x-apple-diskimage",
    "application/x-executable",
    "application/x-mach-binary",
    "application/vnd.debian.binary-package",
    "application/x-redhat-package-manager",
    "application/vnd.android.package-archive",
}

# The raster formats process_image emits/accepts. Only these are served inline
# — a stored-verbatim ``image/svg+xml`` (or other scriptable image type) opened
# top-level could execute script, and attachments are viewable by anyone with
# instance access, so everything else downloads as an attachment.
_INLINE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

router = APIRouter(tags=["attachments"])


def _safe_filename(name: str | None) -> str | None:
    """Strip path components and non-printable characters from a client name."""
    if not name:
        return None
    base = "".join(ch for ch in os.path.basename(name) if ch.isprintable()).strip()
    return base[:255] or None


def _resolve_mime(file: UploadFile, filename: str | None) -> str:
    """Trust the client's Content-Type, falling back to the filename extension."""
    declared = (file.content_type or "").strip().lower()
    if declared and declared != "application/octet-stream":
        return declared[:64]
    guessed, _ = mimetypes.guess_type(filename or "")
    return (guessed or "application/octet-stream")[:64]


def _is_blocked(filename: str | None, mime_type: str) -> bool:
    if mime_type in _BLOCKED_MIME_TYPES:
        return True
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower() in _BLOCKED_EXTENSIONS
    return False


def _content_disposition(filename: str) -> str:
    """RFC 6266 attachment header with an ASCII fallback + UTF-8 form."""
    ascii_name = (
        filename.encode("ascii", "ignore")
        .decode("ascii")
        .replace('"', "")
        .replace("\\", "")
        or "download"
    )
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@router.post("/attachments", response_model=AttachmentResponse)
def upload_attachment(
    agent_instance_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Validate, normalize/store, and record one attachment for a pending message."""
    try:
        instance_uuid = UUID(agent_instance_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent_instance_id")

    filename = _safe_filename(file.filename)
    declared_mime = _resolve_mime(file, filename)
    if _is_blocked(filename, declared_mime):
        raise HTTPException(status_code=400, detail="This file type is not allowed")

    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="File is empty")

    # Images are normalized; anything that isn't a decodable image in an
    # allowed format (PDF, CSV, source, SVG, HEIC, …) is stored verbatim with
    # no dimensions.
    try:
        processed = process_image(raw)
        data = processed.data
        mime_type = processed.mime_type
        width: int | None = processed.width
        height: int | None = processed.height
    except InvalidImageError:
        data = raw
        mime_type = declared_mime
        width = None
        height = None

    attachment_id = uuid4()
    s3_key = storage.attachment_key(str(current_user.id), str(attachment_id), mime_type)
    try:
        storage.upload_attachment(s3_key, data, mime_type)
    except Exception as e:
        logger.exception("attachment upload to S3 failed")
        raise HTTPException(status_code=502, detail="Failed to store file") from e

    try:
        attachment = create_attachment(
            db,
            attachment_id=attachment_id,
            user_id=current_user.id,
            instance_id=instance_uuid,
            s3_key=s3_key,
            mime_type=mime_type,
            size_bytes=len(data),
            width=width,
            height=height,
            original_filename=filename,
        )
        # Snapshot before commit — expire_on_commit makes attribute access
        # after commit unsafe (§2.7).
        response = AttachmentResponse(
            id=str(attachment.id),
            mime_type=attachment.mime_type,
            size_bytes=attachment.size_bytes,
            width=attachment.width,
            height=attachment.height,
            filename=attachment.original_filename,
        )
        db.commit()
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/attachments/{attachment_id}")
def download_attachment(
    attachment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Serve attachment bytes to the uploader or anyone with instance access."""
    attachment = get_attachment_for_user(db, attachment_id, current_user.id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    try:
        data = storage.download_attachment(attachment.s3_key)
    except Exception as e:
        logger.exception("attachment download from S3 failed")
        raise HTTPException(status_code=502, detail="Failed to fetch file") from e

    headers = {
        "Cache-Control": "private, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    }
    # Raster images render inline (the chat lightbox uses <img>); everything
    # else — including scriptable image types like SVG — downloads under its
    # original name so it can't execute in the vicoa-web origin.
    if attachment.mime_type not in _INLINE_IMAGE_TYPES:
        headers["Content-Disposition"] = _content_disposition(
            attachment.original_filename or str(attachment_id)
        )

    return Response(
        content=data,
        media_type=attachment.mime_type,
        headers=headers,
    )
