"""Video playback through the relay: signed stream URLs and the Range proxy.

The fake router stands in for the daemon socket by answering
`read-file-range` with the real daemon handler, so these cover the proxy and
`vicoa.rpc.file_ops.read_file_range` end to end.
"""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from shared.config import settings
from shared.websocket.connection_manager import Connection
from shared.websocket.rpc import RpcError, rpc_router
from servers.api import media
from servers.api.media import (
    SLICE_BYTES,
    TOKEN_TTL_SECONDS,
    MediaClaims,
    media_router,
    mint_media_token,
    verify_media_token,
)
from servers.api.ws_handler import handle_rpc_call
from vicoa.rpc.file_ops import read_file_range


@pytest.fixture(autouse=True)
def signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_private_key", "test-private-key")


class FakeRouter:
    """`rpc_router` with one user's one machine, answering as its daemon would."""

    def __init__(self, user_id: str, machine_id: str) -> None:
        self.owner = (user_id, machine_id)
        self.calls: list[dict] = []

    async def call(
        self, user_id: str, machine_id: str, method: str, params: dict
    ) -> dict:
        if (user_id, machine_id) != self.owner:
            raise RpcError("no_handler")
        assert method == "read-file-range"
        self.calls.append(params)
        return read_file_range(**params)


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> FakeRouter:
    fake = FakeRouter("u1", "m1")
    monkeypatch.setattr(media, "rpc_router", fake)
    return fake


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(media_router, prefix="/api/v1")
    return TestClient(app)


def _url(cwd: Path, path: str, user_id: str = "u1") -> str:
    token = mint_media_token(MediaClaims(user_id, "m1", str(cwd), path, "video/mp4"))
    assert token is not None
    return f"/api/v1/media/{token}"


def test_token_round_trips_and_expires() -> None:
    claims = MediaClaims("u1", "m1", "/proj", "out/demo.mp4", "video/mp4")
    token = mint_media_token(claims, now=1000)
    assert token is not None
    assert verify_media_token(token, now=1000) == claims
    assert verify_media_token(token, now=1000 + TOKEN_TTL_SECONDS + 1) is None


def test_token_rejects_tampering_and_a_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = mint_media_token(MediaClaims("u1", "m1", "/proj", "a.mp4", "video/mp4"))
    assert token is not None
    body, _, sig = token.partition(".")
    other = mint_media_token(MediaClaims("u2", "m1", "/proj", "a.mp4", "video/mp4"))
    assert other is not None
    assert verify_media_token(f"{other.partition('.')[0]}.{sig}") is None
    assert verify_media_token(f"{body}.{sig[:-2]}") is None
    assert verify_media_token("garbage") is None

    # No secret configured: never mint, never accept.
    monkeypatch.setattr(settings, "jwt_private_key", "")
    assert (
        mint_media_token(MediaClaims("u1", "m1", "/proj", "a.mp4", "video/mp4")) is None
    )
    assert verify_media_token(token) is None


async def test_only_a_video_read_file_result_gets_a_stream_url() -> None:
    caller = Connection(
        connection_id=uuid4().hex, user_id="u1", scope="user-scoped", rooms=frozenset()
    )
    daemon = Connection(
        connection_id=uuid4().hex,
        user_id="u1",
        scope="machine-scoped",
        rooms=frozenset(),
        machine_id="m1",
    )
    rpc_router.register("u1", "m1", "read-file", daemon)
    video = {"content": "", "is_binary": True, "size": 4, "mime_type": "video/mp4"}
    text = {"content": "<html>", "is_binary": False, "size": 6}
    disguised = {**text, "mime_type": "text/html"}
    try:
        results = []
        for daemon_result in (video, text, disguised):
            task = asyncio.create_task(
                handle_rpc_call(
                    caller,
                    {
                        "type": "rpc-call",
                        "request_id": "r",
                        "machine_id": "m1",
                        "method": "read-file",
                        "params": {"cwd": "/proj", "path": "a.mp4"},
                    },
                )
            )
            await asyncio.sleep(0)
            request = daemon.outbox.get_nowait()
            rpc_router.resolve(request["corr_id"], dict(daemon_result))
            await task
            results.append(caller.outbox.get_nowait()["result"])
    finally:
        rpc_router.unregister(daemon)

    token = results[0]["stream_url"].removeprefix("/api/v1/media/")
    assert verify_media_token(token) == MediaClaims(
        "u1", "m1", "/proj", "a.mp4", "video/mp4"
    )
    assert "stream_url" not in results[1]
    assert "stream_url" not in results[2]


def test_streams_the_whole_file_across_slices(
    client: TestClient, router: FakeRouter, tmp_path: Path
) -> None:
    data = bytes(range(256)) * (SLICE_BYTES // 256 * 2 + 3)
    (tmp_path / "demo.mp4").write_bytes(data)

    response = client.get(_url(tmp_path, "demo.mp4"))
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == data
    assert [c["offset"] for c in router.calls] == [0, SLICE_BYTES, 2 * SLICE_BYTES]


def test_answers_ranges(client: TestClient, router: FakeRouter, tmp_path: Path) -> None:
    data = bytes(range(256)) * 4
    (tmp_path / "demo.mp4").write_bytes(data)
    url = _url(tmp_path, "demo.mp4")

    probe = client.get(url, headers={"Range": "bytes=0-1"})
    assert probe.status_code == 206
    assert probe.headers["content-range"] == "bytes 0-1/1024"
    assert probe.content == data[:2]
    # A probe reads only what it asked for.
    assert router.calls[-1]["length"] == 2

    tail = client.get(url, headers={"Range": "bytes=1000-"})
    assert tail.status_code == 206
    assert tail.headers["content-range"] == "bytes 1000-1023/1024"
    assert tail.content == data[1000:]

    suffix = client.get(url, headers={"Range": "bytes=-24"})
    assert suffix.headers["content-range"] == "bytes 1000-1023/1024"
    assert suffix.content == data[1000:]

    for bad in ("bytes=2000-", "bytes=10-5"):
        response = client.get(url, headers={"Range": bad})
        assert response.status_code == 416
        assert response.headers["content-range"] == "bytes */1024"


def test_a_file_changing_mid_stream_ends_the_body_short(
    client: TestClient,
    router: FakeRouter,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "demo.mp4"
    target.write_bytes(b"\0" * (SLICE_BYTES * 2))
    real_call = router.call

    async def call_then_touch(*args: object) -> dict:
        result = await real_call(*args)  # type: ignore[arg-type]
        os.utime(target, (1, len(router.calls)))  # a new mtime after every slice
        return result

    monkeypatch.setattr(router, "call", call_then_touch)
    with client.stream("GET", _url(tmp_path, "demo.mp4")) as response:
        body = b"".join(response.iter_raw())
    assert len(body) == SLICE_BYTES


@pytest.mark.usefixtures("router")
def test_refuses_bad_tokens_and_other_users(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "demo.mp4").write_bytes(b"x")
    assert client.get("/api/v1/media/not-a-token").status_code == 401
    # A valid token for another user routes to no daemon of this one's.
    assert client.get(_url(tmp_path, "demo.mp4", user_id="u2")).status_code == 404


@pytest.mark.usefixtures("router")
def test_maps_daemon_refusals_to_statuses(client: TestClient, tmp_path: Path) -> None:
    assert client.get(_url(tmp_path, "missing.mp4")).status_code == 404
    assert client.get(_url(tmp_path, "../x.mp4")).status_code == 403
