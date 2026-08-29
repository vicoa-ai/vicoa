"""Tests for attachment upload/download and message binding."""

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

import shared.storage as storage_module
from backend.models import MAX_ATTACHMENTS_PER_MESSAGE
from shared.database.models import AgentInstance, MessageAttachment, User
from shared.database.enums import AgentStatus


def _png_bytes(width: int = 64, height: int = 48) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color=(200, 50, 50)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def fake_storage(monkeypatch):
    """In-memory stand-in for S3."""
    store: dict[str, tuple[bytes, str]] = {}

    def upload(key: str, data: bytes, mime_type: str) -> None:
        store[key] = (data, mime_type)

    def download(key: str) -> bytes:
        return store[key][0]

    monkeypatch.setattr(storage_module, "upload_attachment", upload)
    monkeypatch.setattr(storage_module, "download_attachment", download)
    return store


def _upload(client, instance_id, content=None, filename="photo.png", mime="image/png"):
    return client.post(
        "/api/v1/attachments",
        data={"agent_instance_id": str(instance_id)},
        files={
            "file": (filename, content if content is not None else _png_bytes(), mime)
        },
    )


class TestAttachmentUpload:
    def test_upload_and_download_roundtrip(
        self, authenticated_client, test_agent_instance, fake_storage
    ):
        resp = _upload(authenticated_client, test_agent_instance.id)
        assert resp.status_code == 200
        body = resp.json()
        # Opaque PNG is re-encoded to JPEG by preprocessing.
        assert body["mime_type"] == "image/jpeg"
        assert body["width"] == 64
        assert body["height"] == 48
        assert len(fake_storage) == 1

        download = authenticated_client.get(f"/api/v1/attachments/{body['id']}")
        assert download.status_code == 200
        assert download.headers["content-type"] == "image/jpeg"
        (stored_bytes, _) = next(iter(fake_storage.values()))
        assert download.content == stored_bytes

    def test_upload_non_image_stored_verbatim(
        self, authenticated_client, test_agent_instance, fake_storage
    ):
        raw = b"%PDF-1.4\nnot really a pdf but not an image either\n"
        resp = _upload(
            authenticated_client,
            test_agent_instance.id,
            content=raw,
            filename="report.pdf",
            mime="application/pdf",
        )
        assert resp.status_code == 200
        body = resp.json()
        # Non-images keep their declared type and carry no dimensions.
        assert body["mime_type"] == "application/pdf"
        assert body["width"] is None
        assert body["height"] is None
        assert body["filename"] == "report.pdf"
        # Stored verbatim — no re-encode.
        (stored_bytes, _) = next(iter(fake_storage.values()))
        assert stored_bytes == raw

        # Non-images download as an attachment, never inline in the origin.
        download = authenticated_client.get(f"/api/v1/attachments/{body['id']}")
        assert download.status_code == 200
        assert "attachment" in download.headers.get("content-disposition", "")

    def test_upload_rejects_blocked_type(
        self, authenticated_client, test_agent_instance, fake_storage
    ):
        resp = _upload(
            authenticated_client,
            test_agent_instance.id,
            content=b"MZ\x90\x00binary",
            filename="tool.exe",
            mime="application/octet-stream",
        )
        assert resp.status_code == 400
        assert not fake_storage

    def test_upload_rejects_oversize(
        self, authenticated_client, test_agent_instance, fake_storage
    ):
        resp = _upload(
            authenticated_client,
            test_agent_instance.id,
            content=b"x" * (25 * 1024 * 1024 + 1),
            filename="big.bin",
            mime="application/octet-stream",
        )
        assert resp.status_code == 413
        assert not fake_storage

    def test_upload_unknown_instance_404(self, authenticated_client, fake_storage):
        resp = _upload(authenticated_client, uuid4())
        assert resp.status_code == 404


class TestMessageAttachmentBinding:
    def test_send_message_with_attachments(
        self, authenticated_client, test_agent_instance, test_db, fake_storage
    ):
        ids = [
            _upload(authenticated_client, test_agent_instance.id).json()["id"]
            for _ in range(2)
        ]

        resp = authenticated_client.post(
            f"/api/v1/agent-instances/{test_agent_instance.id}/messages",
            json={"content": "look at these", "attachment_ids": ids},
        )
        assert resp.status_code == 200
        meta = resp.json()["message_metadata"]
        assert [a["id"] for a in meta["attachments"]] == ids
        assert meta["attachments"][0]["mime_type"] == "image/jpeg"

        rows = (
            test_db.query(MessageAttachment)
            .filter(MessageAttachment.message_id == resp.json()["id"])
            .all()
        )
        assert len(rows) == 2

    def test_attachment_cannot_be_reused(
        self, authenticated_client, test_agent_instance, fake_storage
    ):
        attachment_id = _upload(authenticated_client, test_agent_instance.id).json()[
            "id"
        ]
        first = authenticated_client.post(
            f"/api/v1/agent-instances/{test_agent_instance.id}/messages",
            json={"content": "first", "attachment_ids": [attachment_id]},
        )
        assert first.status_code == 200

        second = authenticated_client.post(
            f"/api/v1/agent-instances/{test_agent_instance.id}/messages",
            json={"content": "second", "attachment_ids": [attachment_id]},
        )
        assert second.status_code == 404

    def test_exceeding_attachment_limit_is_rejected(
        self, authenticated_client, test_agent_instance
    ):
        over_limit = [str(uuid4()) for _ in range(MAX_ATTACHMENTS_PER_MESSAGE + 1)]
        resp = authenticated_client.post(
            f"/api/v1/agent-instances/{test_agent_instance.id}/messages",
            json={"content": "too many", "attachment_ids": over_limit},
        )
        assert resp.status_code == 422

    def test_at_the_attachment_limit_is_accepted(
        self, authenticated_client, test_agent_instance, fake_storage
    ):
        """The cap is off-by-one sensitive: N must pass where N+1 is rejected."""
        ids = [
            _upload(authenticated_client, test_agent_instance.id).json()["id"]
            for _ in range(MAX_ATTACHMENTS_PER_MESSAGE)
        ]
        resp = authenticated_client.post(
            f"/api/v1/agent-instances/{test_agent_instance.id}/messages",
            json={"content": "exactly at the cap", "attachment_ids": ids},
        )
        assert resp.status_code == 200

    def test_send_with_invalid_attachment_id_400(
        self, authenticated_client, test_agent_instance
    ):
        resp = authenticated_client.post(
            f"/api/v1/agent-instances/{test_agent_instance.id}/messages",
            json={"content": "hi", "attachment_ids": ["not-a-uuid"]},
        )
        assert resp.status_code == 400


class TestAttachmentAccess:
    def test_foreign_attachment_not_downloadable_or_bindable(
        self,
        authenticated_client,
        test_agent_instance,
        test_db,
        test_user_agent,
        fake_storage,
    ):
        other_user = User(
            id=uuid4(),
            email="other@example.com",
            display_name="Other",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        other_instance = AgentInstance(
            id=uuid4(),
            user_agent_id=test_user_agent.id,
            user_id=other_user.id,
            status=AgentStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
        )
        foreign = MessageAttachment(
            id=uuid4(),
            user_id=other_user.id,
            agent_instance_id=other_instance.id,
            s3_key="attachments/other/foreign.jpg",
            mime_type="image/jpeg",
            size_bytes=10,
            width=1,
            height=1,
            original_filename="foreign.jpg",
        )
        test_db.add_all([other_user, other_instance])
        test_db.commit()
        test_db.add(foreign)
        test_db.commit()

        download = authenticated_client.get(f"/api/v1/attachments/{foreign.id}")
        assert download.status_code == 404

        bind = authenticated_client.post(
            f"/api/v1/agent-instances/{test_agent_instance.id}/messages",
            json={"content": "steal", "attachment_ids": [str(foreign.id)]},
        )
        assert bind.status_code == 404
