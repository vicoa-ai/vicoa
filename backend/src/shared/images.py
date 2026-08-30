"""Server-side validation and normalization for uploaded message images.

Every re-encoded image loses its EXIF (including GPS) by construction.
GIFs are the exception: re-encoding would flatten animation, so the
uploaded bytes are stored verbatim. GIF carries no EXIF, but its Comment
and Application extension blocks (where XMP lives) do survive — the
metadata guarantee does not extend to GIF.

Decoding is the one step whose cost tracks the image rather than the file:
a 113KB PNG can expand into a 108MB bitmap, so a byte-size limit bounds
nothing. Every gate that the file header can answer — is the format
allowed, how many pixels — therefore runs before `load()`.
"""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_LONG_EDGE = 2048
JPEG_QUALITY = 85

# Bitmap memory is width * height * channels, independent of file size.
# 50MP admits a 48MP phone photo while capping an RGBA decode at ~200MB.
MAX_PIXELS = 50_000_000

_REENCODED_FORMATS = {"JPEG", "PNG", "WEBP"}


class InvalidImageError(ValueError):
    """Uploaded bytes are not a decodable image in an allowed format."""


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    mime_type: str
    width: int
    height: int


def process_image(raw: bytes) -> ProcessedImage:
    """Decode, EXIF-correct, strip metadata, downscale, and re-encode."""
    try:
        # Parses the header only — no pixel buffer is allocated yet.
        img = Image.open(BytesIO(raw))
    except Image.DecompressionBombError as e:
        raise InvalidImageError(f"image too large: {e}") from e
    except (UnidentifiedImageError, OSError) as e:
        raise InvalidImageError(f"not a decodable image: {e}") from e

    fmt = (img.format or "").upper()
    if fmt != "GIF" and fmt not in _REENCODED_FORMATS:
        raise InvalidImageError(f"unsupported image format: {fmt or 'unknown'}")

    if img.width * img.height > MAX_PIXELS:
        raise InvalidImageError(
            f"image has too many pixels: {img.width}x{img.height} exceeds {MAX_PIXELS}"
        )

    # JPEG only, and only before load(): decode at a reduced DCT scale.
    # draft() picks the largest power-of-two reduction that still leaves the
    # result above MAX_LONG_EDGE, so thumbnail() keeps resample headroom.
    img.draft(None, (MAX_LONG_EDGE, MAX_LONG_EDGE))

    try:
        img.load()
    except OSError as e:
        raise InvalidImageError(f"not a decodable image: {e}") from e

    if fmt == "GIF":
        # Re-encoding would flatten animation, so the original bytes are stored
        # as-is. The load() above still proves they decode.
        return ProcessedImage(raw, "image/gif", img.width, img.height)

    if max(img.size) > MAX_LONG_EDGE:
        img.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.Resampling.LANCZOS)

    # Transposing after the downscale is equivalent — a quarter turn swaps the
    # axes but not the long edge — and rotates 4MP instead of 48MP. in_place
    # skips the full-resolution copy exif_transpose makes even when there is
    # no orientation tag to apply.
    ImageOps.exif_transpose(img, in_place=True)

    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    out = BytesIO()
    if has_alpha:
        # convert() to the mode an image already has still copies it.
        rgba = img if img.mode == "RGBA" else img.convert("RGBA")
        rgba.save(out, format="PNG")
        mime = "image/png"
    else:
        rgb = img if img.mode == "RGB" else img.convert("RGB")
        rgb.save(out, format="JPEG", quality=JPEG_QUALITY)
        mime = "image/jpeg"
    return ProcessedImage(out.getvalue(), mime, img.width, img.height)
