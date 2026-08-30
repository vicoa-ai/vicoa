"""Unit tests for shared.storage key derivation."""

from shared.storage import attachment_key


class TestAttachmentKey:
    def test_known_image_mimes_get_real_extensions(self):
        assert (
            attachment_key("user-1", "att-1", "image/jpeg")
            == "attachments/user-1/att-1.jpg"
        )
        assert (
            attachment_key("user-1", "att-1", "image/png")
            == "attachments/user-1/att-1.png"
        )
        assert (
            attachment_key("user-1", "att-1", "image/gif")
            == "attachments/user-1/att-1.gif"
        )
        assert (
            attachment_key("user-1", "att-1", "image/webp")
            == "attachments/user-1/att-1.webp"
        )

    def test_unknown_mime_falls_back_to_bin_instead_of_raising(self):
        """Non-image types must not KeyError — this is what unblocks file uploads."""
        assert (
            attachment_key("user-1", "att-1", "application/pdf")
            == "attachments/user-1/att-1.bin"
        )
        assert (
            attachment_key("user-1", "att-1", "text/plain")
            == "attachments/user-1/att-1.bin"
        )

    def test_key_is_scoped_by_user(self):
        a = attachment_key("user-a", "same-id", "image/png")
        b = attachment_key("user-b", "same-id", "image/png")
        assert a != b
        assert a.startswith("attachments/user-a/")
        assert b.startswith("attachments/user-b/")
