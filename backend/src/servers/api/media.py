"""Project video playback through the relay, for clients off the machine.

The daemon's `read-file` tags a video with `mime_type`; `attach_stream_url`
adds a `stream_url` signed for that user, machine and file as the result
passes through. The player then loads `GET /api/v1/media/{token}` with
ordinary HTTP Range requests, and each range is read off the daemon in
`read-file-range` slices and streamed back, so a video plays and seeks
without the whole file crossing the relay first.

A `<video>` element can't send a bearer token, hence the signed URL. The token
carries its own claims (no server-side state) and is checked on every range,
and every slice still goes through `rpc_router`'s `(user_id, machine_id)` key,
so a token only ever reaches its own user's daemon.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from shared.config import settings
from shared.websocket.rpc import RpcError, rpc_router

logger = logging.getLogger(__name__)

media_router = APIRouter(tags=["media"])

# How long a minted URL plays. A tab left open longer fails its next range and
# shows the fallback card; reopening the file mints a fresh one.
TOKEN_TTL_SECONDS = 12 * 60 * 60

# Bytes asked of the daemon per `read-file-range` call: its own cap
# (`_RANGE_CAP` in vicoa/rpc/file_ops.py). It may return less; the stream
# advances by what actually came back.
SLICE_BYTES = 1024 * 1024

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


@dataclass(frozen=True)
class MediaClaims:
    user_id: str
    machine_id: str
    cwd: str
    path: str
    media_type: str


def _signing_key() -> bytes | None:
    # Derived from the agent-key signing secret with its own label, so a media
    # signature can't stand in for anything else that secret signs.
    if not settings.jwt_private_key:
        return None
    return hashlib.sha256(
        b"vicoa-media-url\0" + settings.jwt_private_key.encode()
    ).digest()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint_media_token(claims: MediaClaims, now: float | None = None) -> str | None:
    key = _signing_key()
    if key is None:
        return None
    payload = {
        "u": claims.user_id,
        "m": claims.machine_id,
        "c": claims.cwd,
        "p": claims.path,
        "t": claims.media_type,
        "e": int((time.time() if now is None else now) + TOKEN_TTL_SECONDS),
    }
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url(hmac.new(key, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_media_token(token: str, now: float | None = None) -> MediaClaims | None:
    key = _signing_key()
    body, _, sig = token.partition(".")
    if key is None or not body or not sig:
        return None
    expected = _b64url(hmac.new(key, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_unb64url(body))
        claims = MediaClaims(
            user_id=str(payload["u"]),
            machine_id=str(payload["m"]),
            cwd=str(payload["c"]),
            path=str(payload["p"]),
            media_type=str(payload["t"]),
        )
        expires = int(payload["e"])
    except (binascii.Error, ValueError, KeyError, TypeError):
        return None
    if expires < (time.time() if now is None else now):
        return None
    return claims


def attach_stream_url(
    user_id: str, machine_id: str, params: dict, result: dict
) -> None:
    """Add `stream_url` to a `read-file` result for a video, in place.

    A path, not an absolute URL: behind the proxy this process can't be sure of
    its own public scheme and host, and the client already knows them (it is
    holding a socket to this server). Only `video/*` is ever signed, so the
    proxy can't be talked into serving a repo's HTML as a page.
    """
    media_type = result.get("mime_type")
    if not isinstance(media_type, str) or not media_type.startswith("video/"):
        return
    cwd, path = params.get("cwd"), params.get("path")
    if not isinstance(cwd, str) or not isinstance(path, str):
        return
    token = mint_media_token(MediaClaims(user_id, machine_id, cwd, path, media_type))
    if token is not None:
        result["stream_url"] = f"/api/v1/media/{token}"


async def _read_slice(claims: MediaClaims, offset: int, length: int) -> dict:
    return await rpc_router.call(
        claims.user_id,
        claims.machine_id,
        "read-file-range",
        {"cwd": claims.cwd, "path": claims.path, "offset": offset, "length": length},
    )


def _slice_bytes(result: dict) -> bytes:
    return base64.b64decode(result.get("content") or "")


async def _stream(
    claims: MediaClaims, offset: int, end: int, first: dict
) -> AsyncIterator[bytes]:
    """Bytes `offset..end` (inclusive), starting from the already-read `first`.

    The next slice is requested before the current one is yielded, so the
    daemon round trip overlaps the client's read. A seek drops the connection,
    which cancels this generator and the slice in flight with it. A file that
    changes mid-stream ends the body short rather than splicing two versions.
    """
    mtime = first.get("mtime")
    chunk = _slice_bytes(first)
    pending: asyncio.Task[dict] | None = None
    try:
        while chunk:
            chunk = chunk[: end + 1 - offset]
            next_offset = offset + len(chunk)
            if next_offset <= end:
                pending = asyncio.create_task(
                    _read_slice(
                        claims, next_offset, min(SLICE_BYTES, end + 1 - next_offset)
                    )
                )
            yield chunk
            if pending is None:
                return
            result = await pending
            pending = None
            if result.get("error") or result.get("mtime") != mtime:
                logger.info("media stream stopped: %s", result.get("error", "changed"))
                return
            offset, chunk = next_offset, _slice_bytes(result)
    except RpcError as exc:
        # Headers are already out; ending short is all that's left. The player
        # sees a truncated body and reports an error.
        logger.info("media stream stopped: %s", exc.code)
    finally:
        if pending is not None:
            pending.cancel()


async def _call(claims: MediaClaims, offset: int, length: int) -> dict:
    """One slice before the response starts, so failures still get a status."""
    try:
        result = await _read_slice(claims, offset, length)
    except RpcError as exc:
        status_code = {"no_handler": 404, "timeout": 504}.get(exc.code, 503)
        raise HTTPException(status_code=status_code, detail=exc.code) from exc
    error = result.get("error")
    if error:
        status_code = {
            "outside_project": 403,
            "permission_denied": 403,
            "invalid_range": 416,
        }.get(str(error), 404)
        raise HTTPException(status_code=status_code, detail=str(error))
    return result


@media_router.get("/media/{token}")
async def get_media(token: str, request: Request) -> Response:
    claims = verify_media_token(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="invalid_or_expired")

    # One `bytes=first-last` range (either end optional); anything else, such
    # as a multi-range, gets the whole file, which HTTP allows.
    range_header = request.headers.get("range")
    match = _RANGE_RE.match(range_header.strip()) if range_header else None
    first_pos = int(match.group(1)) if match and match.group(1) else None
    last_pos = int(match.group(2)) if match and match.group(2) else None
    if match and first_pos is None and last_pos is None:
        match = None

    if first_pos is None and last_pos is not None:
        # A suffix range (`bytes=-500`) needs the size first.
        size = int((await _call(claims, 0, 1))["size"])
        start, end = max(0, size - last_pos), size - 1
    else:
        start = first_pos or 0
        end = last_pos if last_pos is not None else start + SLICE_BYTES - 1
    # Read only what was asked for: players probe with tiny ranges.
    first = await _call(claims, start, max(1, min(SLICE_BYTES, end - start + 1)))
    size = int(first["size"])
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-cache",
        "X-Content-Type-Options": "nosniff",
    }
    if size == 0 and match is None:
        return Response(b"", media_type=claims.media_type, headers=headers)
    end = size - 1 if last_pos is None else min(end, size - 1)
    if start >= size or end < start:
        headers["Content-Range"] = f"bytes */{size}"
        return Response(status_code=416, headers=headers)

    headers["Content-Length"] = str(end - start + 1)
    if match:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        _stream(claims, start, end, first),
        status_code=206 if match else 200,
        media_type=claims.media_type,
        headers=headers,
    )
