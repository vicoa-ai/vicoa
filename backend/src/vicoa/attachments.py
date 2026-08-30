"""Shared helpers for delivering attachments to agent processes.

User messages may carry ``message_metadata["attachments"]`` — a list of
``{id, mime_type, size_bytes, width, height, filename}`` dicts stamped by
the backend at send time. Attachments may be images or arbitrary files.
Integrations use these helpers to parse that shape defensively, fetch bytes
through their Vicoa client, and (where the agent wants a file path rather
than inline bytes) persist them under ``~/.vicoa/attachments/<instance_id>/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def is_image_mime(mime_type: str | None) -> bool:
    return bool(mime_type) and mime_type.startswith("image/")


def _extension_for(mime_type: str, filename: str | None) -> str:
    """Best on-disk extension: image map, else the original file's suffix.

    A real suffix (``.pdf``, ``.csv``) is what lets the agent's file tools
    treat the bytes correctly; ``.bin`` is only the last resort. The suffix
    is constrained to short alphanumerics so a hostile filename can't inject
    path or shell metacharacters into the on-disk name.
    """
    if mime_type in _EXT_BY_MIME:
        return _EXT_BY_MIME[mime_type]
    if filename:
        suffix = Path(filename).suffix.lstrip(".").lower()
        if suffix.isalnum() and 0 < len(suffix) <= 8:
            return suffix
    return "bin"


@dataclass(frozen=True)
class AttachmentRef:
    id: str
    mime_type: str
    filename: str | None


@dataclass(frozen=True)
class LocalAttachment:
    id: str
    mime_type: str
    path: Path
    filename: str | None = None


def extract_attachment_refs(message_metadata: Any) -> list[AttachmentRef]:
    """Parse ``message_metadata.attachments``; unknown/malformed shapes -> []."""
    if not isinstance(message_metadata, dict):
        return []
    raw = message_metadata.get("attachments")
    if not isinstance(raw, list):
        return []
    refs: list[AttachmentRef] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        mime = item.get("mime_type")
        filename = item.get("filename")
        refs.append(
            AttachmentRef(
                id=item["id"],
                mime_type=mime if isinstance(mime, str) else "application/octet-stream",
                filename=filename if isinstance(filename, str) else None,
            )
        )
    return refs


def attachments_dir(instance_id: str) -> Path:
    directory = Path.home() / ".vicoa" / "attachments" / instance_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_attachment(
    dest_dir: Path, ref: AttachmentRef, data: bytes, mime_type: str
) -> LocalAttachment:
    ext = _extension_for(mime_type, ref.filename)
    path = dest_dir / f"{ref.id}.{ext}"
    path.write_bytes(data)
    return LocalAttachment(
        id=ref.id, mime_type=mime_type, path=path, filename=ref.filename
    )


def attachment_note(local: LocalAttachment) -> str:
    """Path reference appended to prompt text for path-based agents.

    Images keep the wording Claude's vision-capable Read tool expects; other
    files name the original filename so the agent knows what it's opening.
    """
    if is_image_mime(local.mime_type):
        return f"[Attached image: {local.path}]"
    name = local.filename or local.path.name
    return f"[Attached file {name}: {local.path}]"


def unavailable_note(ref: AttachmentRef) -> str:
    """Tells the agent an attachment was meant to be sent but couldn't be fetched."""
    label = "Image" if is_image_mime(ref.mime_type) else "File"
    return f"[{label} attachment unavailable: {ref.filename or ref.id}]"
