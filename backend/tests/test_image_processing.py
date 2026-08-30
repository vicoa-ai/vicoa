"""Unit tests for shared.images.process_image (message attachment preprocessing)."""

from io import BytesIO

import pytest
from PIL import Image, ImageFile

from shared import images
from shared.images import (
    MAX_LONG_EDGE,
    MAX_PIXELS,
    InvalidImageError,
    ProcessedImage,
    process_image,
)


def _forbid_decode(monkeypatch):
    """Make any pixel decode an error, so 'rejected' can be told apart
    from 'rejected, but only after allocating the bitmap'."""

    def _boom(self, *args, **kwargs):
        raise AssertionError("image was decoded before it was rejected")

    monkeypatch.setattr(ImageFile.ImageFile, "load", _boom)


def _jpeg_bytes(width: int, height: int, exif: Image.Exif | None = None) -> bytes:
    buf = BytesIO()
    img = Image.new("RGB", (width, height), color=(120, 30, 30))
    if exif is not None:
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def _png_rgba_bytes(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (width, height), color=(0, 100, 0, 128)).save(buf, format="PNG")
    return buf.getvalue()


def _gif_bytes() -> bytes:
    buf = BytesIO()
    Image.new("P", (8, 8)).save(buf, format="GIF")
    return buf.getvalue()


def _webp_bytes(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color=(10, 10, 200)).save(buf, format="WEBP")
    return buf.getvalue()


def test_jpeg_reencoded_with_exif_stripped_and_orientation_applied():
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90 CW to display
    exif[0x010F] = "TestMake"  # arbitrary metadata that must not survive
    raw = _jpeg_bytes(100, 50, exif=exif)

    result = process_image(raw)

    assert isinstance(result, ProcessedImage)
    assert result.mime_type == "image/jpeg"
    # Orientation 6 swaps the displayed dimensions.
    assert (result.width, result.height) == (50, 100)
    out = Image.open(BytesIO(result.data))
    assert (out.width, out.height) == (50, 100)
    assert dict(out.getexif()) == {}


def test_large_image_downscaled_to_max_long_edge():
    raw = _jpeg_bytes(3000, 1000)

    result = process_image(raw)

    assert max(result.width, result.height) == MAX_LONG_EDGE
    # Aspect ratio preserved (3:1) within rounding.
    assert abs(result.width / result.height - 3.0) < 0.02


def test_small_image_not_upscaled():
    raw = _jpeg_bytes(40, 30)

    result = process_image(raw)

    assert (result.width, result.height) == (40, 30)


def test_png_with_alpha_stays_png():
    raw = _png_rgba_bytes(10, 10)

    result = process_image(raw)

    assert result.mime_type == "image/png"
    assert Image.open(BytesIO(result.data)).mode == "RGBA"


def test_webp_reencoded_to_jpeg():
    raw = _webp_bytes(10, 10)

    result = process_image(raw)

    assert result.mime_type == "image/jpeg"


def test_gif_passes_through_unmodified():
    raw = _gif_bytes()

    result = process_image(raw)

    assert result.mime_type == "image/gif"
    assert result.data == raw
    assert (result.width, result.height) == (8, 8)


def test_non_image_bytes_rejected():
    with pytest.raises(InvalidImageError):
        process_image(b"definitely not an image")


def test_truncated_image_rejected():
    raw = _jpeg_bytes(200, 200)
    with pytest.raises(InvalidImageError):
        process_image(raw[: len(raw) // 2])


def test_unsupported_format_rejected():
    buf = BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="BMP")
    with pytest.raises(InvalidImageError):
        process_image(buf.getvalue())


def test_unsupported_format_rejected_without_decoding(monkeypatch):
    buf = BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="BMP")
    raw = buf.getvalue()

    _forbid_decode(monkeypatch)
    with pytest.raises(InvalidImageError, match="unsupported image format"):
        process_image(raw)


def test_excessive_pixel_count_rejected_without_decoding(monkeypatch):
    raw = _jpeg_bytes(64, 64)  # 4096 px

    monkeypatch.setattr(images, "MAX_PIXELS", 100)
    _forbid_decode(monkeypatch)
    with pytest.raises(InvalidImageError, match="too many pixels"):
        process_image(raw)


def test_oversized_gif_rejected_without_decoding(monkeypatch):
    """GIFs pass through unmodified, so they must still be pixel-bounded."""
    buf = BytesIO()
    Image.new("P", (64, 64)).save(buf, format="GIF")
    raw = buf.getvalue()

    monkeypatch.setattr(images, "MAX_PIXELS", 100)
    _forbid_decode(monkeypatch)
    with pytest.raises(InvalidImageError, match="too many pixels"):
        process_image(raw)


def test_decompression_bomb_raises_invalid_image_not_bare_exception(monkeypatch):
    """Pillow's DecompressionBombError subclasses Exception, not OSError, so it
    escaped the old handler and surfaced as an unhandled 500."""
    raw = _jpeg_bytes(64, 64)

    # Pillow raises above 2 * MAX_IMAGE_PIXELS, inside Image.open().
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    with pytest.raises(InvalidImageError, match="image too large"):
        process_image(raw)


def test_pixel_budget_admits_a_48mp_phone_photo():
    assert 8064 * 6048 <= MAX_PIXELS
