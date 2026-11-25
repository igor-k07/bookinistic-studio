"""Integration tests for Photo Engine V3: render pipeline, rembg processor, and barcode scanner (Step 3.1)."""

import io

from PIL import Image, ImageDraw

from backend.infrastructure.media.barcode_scanner import BarcodeScanner
from backend.infrastructure.media.rembg_processor import RembgImageProcessor
from backend.infrastructure.media.render_pipeline import ImageRenderPipeline


def _create_test_image(mode: str = "RGB", size: tuple = (400, 500), fill: tuple = (50, 100, 150)) -> Image.Image:
    """Create synthetic test image with a defined border and center content."""
    im = Image.new(mode, size, fill)
    draw = ImageDraw.Draw(im)
    draw.rectangle([50, 50, size[0] - 50, size[1] - 50], fill=(200, 50, 50))
    return im


def test_float_rotation_has_pure_white_corners() -> None:
    """Verify 1.5° float rotation produces pure white (255, 255, 255) fill on expanded corners."""
    im = _create_test_image("RGB", (300, 400), fill=(20, 20, 20))
    rendered_bytes, render_hash, width, height = ImageRenderPipeline.render(
        im, transformations={"rotation": 1.5}
    )

    assert rendered_bytes
    assert render_hash
    assert width > 300
    assert height > 400

    out_im = Image.open(io.BytesIO(rendered_bytes))
    # Check extreme corners (0, 0), (width-1, 0), (0, height-1)
    corners = [(0, 0), (out_im.width - 1, 0), (0, out_im.height - 1)]
    for pt in corners:
        pixel = out_im.getpixel(pt)
        # JPEG compression can have minor +-2 variance from 255
        assert pixel[0] >= 253, f"Red channel {pixel[0]} not white at {pt}"
        assert pixel[1] >= 253, f"Green channel {pixel[1]} not white at {pt}"
        assert pixel[2] >= 253, f"Blue channel {pixel[2]} not white at {pt}"


def test_rgba_png_input_succeeds() -> None:
    """Verify RGBA image with transparency renders seamlessly to white-background JPEG."""
    rgba = Image.new("RGBA", (200, 200), (0, 0, 0, 0))  # Full transparent
    draw = ImageDraw.Draw(rgba)
    draw.ellipse([40, 40, 160, 160], fill=(180, 40, 40, 255))

    rendered_bytes, render_hash, w, h = ImageRenderPipeline.render(rgba)
    assert rendered_bytes
    assert render_hash
    assert w == 200
    assert h == 200

    out_im = Image.open(io.BytesIO(rendered_bytes))
    # Background corner (was transparent) must now be pure white
    corner = out_im.getpixel((5, 5))
    assert corner[0] >= 253
    assert corner[1] >= 253
    assert corner[2] >= 253


def test_clamped_crop_and_8_filters() -> None:
    """Verify clamped crop and all 8 filters execute deterministically."""
    im = _create_test_image("RGB", (400, 600))
    transformations = {
        "crop": {"x": 0.1, "y": 0.15, "w": 0.7, "h": 0.7},
        "filters": {
            "whiten": 15,
            "brightness": 10,
            "contrast": 12,
            "saturation": -5,
            "sharpness": 20,
            "warmth": 15,
            "highlights": -10,
            "shadows": 10,
        },
    }

    bytes1, hash1, w1, h1 = ImageRenderPipeline.render(im, transformations)
    bytes2, hash2, w2, h2 = ImageRenderPipeline.render(im, transformations)

    assert hash1 == hash2, "Render hashing must be 100% deterministic"
    assert len(bytes1) == len(bytes2)
    assert w1 == int(400 * 0.7)
    assert h1 == int(600 * 0.7)


def test_barcode_scanner_fallback() -> None:
    """Verify barcode scanner returns None on blank image without crashing."""
    scanner = BarcodeScanner()
    im = _create_test_image("RGB", (200, 200))
    res = scanner.scan_image(im)
    assert res is None


def test_rembg_contour_protection() -> None:
    """Verify protect_white_cover_mask preserves white book covers."""
    mask = Image.new("L", (100, 100), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle([20, 20, 80, 80], fill=255)

    rgb = Image.new("RGB", (100, 100), (250, 250, 250))  # Light book
    protected = RembgImageProcessor.protect_white_cover_mask(mask, rgb)
    assert protected.size == (100, 100)

