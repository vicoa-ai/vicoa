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
