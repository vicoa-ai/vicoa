"""Thin S3 wrapper for message image attachments.

Credentials come from settings (.env / Fly secrets); when the credential
fields are empty, boto3's default chain (IAM role, ~/.aws/credentials,
real env vars) applies. Kept import-light so the module can be
monkeypatched in tests without AWS configuration.
"""

from typing import Any

import boto3

from shared.config.settings import settings

ATTACHMENTS_BUCKET = "vicoa"

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def attachment_key(user_id: str, attachment_id: str, mime_type: str) -> str:
    # The extension is cosmetic — the key is addressed by id, and the served
    # Content-Type comes from the DB row. Unknown types fall back to .bin
    # rather than raising, matching vicoa.attachments.save_attachment.
    ext = _EXT_BY_MIME.get(mime_type, "bin")
    return f"attachments/{user_id}/{attachment_id}.{ext}"


def project_icon_key(project_id: str) -> str:
    # Keyed by project_id ALONE (not {user_id}/…): a project may later move to a
    # team, so the object path must not encode a single owner (plan §9). No
    # extension — the served Content-Type comes from the stored object's own
    # metadata (download_object), so one deterministic key survives png↔jpeg
    # re-encodes across uploads.
    return f"project-icons/{project_id}"


def _client():
    kwargs: dict[str, Any] = {}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    if settings.aws_region:
        kwargs["region_name"] = settings.aws_region
    return boto3.client("s3", **kwargs)


def upload_attachment(key: str, data: bytes, mime_type: str) -> None:
    _client().put_object(
        Bucket=ATTACHMENTS_BUCKET,
        Key=key,
        Body=data,
        ContentType=mime_type,
    )


def download_attachment(key: str) -> bytes:
    obj = _client().get_object(Bucket=ATTACHMENTS_BUCKET, Key=key)
    return obj["Body"].read()


def download_object(key: str) -> tuple[bytes, str]:
    """Fetch bytes plus the stored Content-Type (for keys with no DB mime row)."""
    obj = _client().get_object(Bucket=ATTACHMENTS_BUCKET, Key=key)
    return obj["Body"].read(), obj.get("ContentType") or "application/octet-stream"


def delete_object(key: str) -> None:
    _client().delete_object(Bucket=ATTACHMENTS_BUCKET, Key=key)
