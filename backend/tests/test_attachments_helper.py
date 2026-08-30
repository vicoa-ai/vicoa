"""Unit tests for vicoa.attachments (agent-side delivery helpers)."""

from vicoa.attachments import (
    AttachmentRef,
    attachment_note,
    extract_attachment_refs,
    save_attachment,
    unavailable_note,
)


class TestExtractAttachmentRefs:
    def test_valid_metadata(self):
        metadata = {
            "attachments": [
                {
                    "id": "abc-123",
                    "mime_type": "image/png",
                    "size_bytes": 10,
                    "width": 4,
                    "height": 4,
                    "filename": "photo.png",
                },
                {"id": "def-456", "mime_type": "image/jpeg", "filename": None},
            ]
        }
        refs = extract_attachment_refs(metadata)
        assert refs == [
            AttachmentRef(id="abc-123", mime_type="image/png", filename="photo.png"),
            AttachmentRef(id="def-456", mime_type="image/jpeg", filename=None),
        ]

    def test_none_and_missing(self):
        assert extract_attachment_refs(None) == []
        assert extract_attachment_refs({}) == []
        assert extract_attachment_refs({"attachments": None}) == []

    def test_malformed_entries_skipped(self):
        metadata = {
            "attachments": [
                "not-a-dict",
                {"no_id": True},
                {"id": 42},
                {"id": "ok-1", "mime_type": 99},
            ]
        }
        refs = extract_attachment_refs(metadata)
        # The only salvageable entry keeps a safe default mime type. It defaults
        # to a generic binary type, not an image, so a mis-tagged file isn't
        # delivered as an image.
        assert refs == [
            AttachmentRef(
                id="ok-1", mime_type="application/octet-stream", filename=None
            )
        ]

    def test_non_dict_metadata(self):
        assert extract_attachment_refs("garbage") == []
        assert extract_attachment_refs(["list"]) == []


class TestSaveAttachment:
    def test_writes_bytes_with_mime_extension(self, tmp_path):
        ref = AttachmentRef(id="att-1", mime_type="image/png", filename="x.png")
        local = save_attachment(tmp_path, ref, b"\x89PNG...", "image/png")
        assert local.path == tmp_path / "att-1.png"
        assert local.path.read_bytes() == b"\x89PNG..."

    def test_unknown_mime_gets_bin_extension(self, tmp_path):
        ref = AttachmentRef(id="att-2", mime_type="application/x-foo", filename=None)
        local = save_attachment(tmp_path, ref, b"data", "application/x-foo")
        assert local.path.suffix == ".bin"

    def test_non_image_keeps_original_extension(self, tmp_path):
        ref = AttachmentRef(
            id="att-6", mime_type="application/pdf", filename="report.pdf"
        )
        local = save_attachment(tmp_path, ref, b"%PDF", "application/pdf")
        assert local.path == tmp_path / "att-6.pdf"


class TestNotes:
    def test_attachment_note_contains_path(self, tmp_path):
        ref = AttachmentRef(id="att-3", mime_type="image/jpeg", filename=None)
        local = save_attachment(tmp_path, ref, b"d", "image/jpeg")
        assert str(local.path) in attachment_note(local)

    def test_image_note_says_image(self, tmp_path):
        ref = AttachmentRef(id="att-7", mime_type="image/png", filename="a.png")
        local = save_attachment(tmp_path, ref, b"d", "image/png")
        assert "Attached image" in attachment_note(local)

    def test_file_note_names_the_file(self, tmp_path):
        ref = AttachmentRef(id="att-8", mime_type="application/pdf", filename="a.pdf")
        local = save_attachment(tmp_path, ref, b"d", "application/pdf")
        note = attachment_note(local)
        assert "Attached file" in note and "a.pdf" in note

    def test_unavailable_note_prefers_filename(self):
        ref = AttachmentRef(id="att-4", mime_type="image/jpeg", filename="cat.jpg")
        assert "cat.jpg" in unavailable_note(ref)
        ref_no_name = AttachmentRef(id="att-5", mime_type="image/jpeg", filename=None)
        assert "att-5" in unavailable_note(ref_no_name)
