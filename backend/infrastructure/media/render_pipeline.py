"""Unified Pillow render pipeline for Photo Engine V3.

Implements float rotation with pure white corners (fillcolor=(255,255,255)),
clamped relative cropping, 8 photo filters, and SHA-256 render hashing.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


class ImageRenderPipeline:
    """Unified, deterministic Pillow rendering pipeline."""

    @staticmethod
    def calculate_hash(data: bytes) -> str:
        """Calculate SHA-256 hash of rendered output bytes."""
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def render(
        cls,
        source: Union[bytes, Path, str, Image.Image],
        transformations: Optional[Dict[str, Any]] = None,
        jpeg_quality: int = 90,
    ) -> Tuple[bytes, str, int, int]:
        """Apply full transformation chain to image and return (jpeg_bytes, sha256_hash, width, height).

        Chain: EXIF orientation -> RGB conversion -> Float rotation (fillcolor=white)
               -> Clamped crop -> 8 Filters -> JPEG Q90 encoding.
        """
        trans = transformations or {}

        # 1. Load image and apply EXIF orientation
        if isinstance(source, Image.Image):
            im = source.copy()
        elif isinstance(source, bytes):
            im = Image.open(io.BytesIO(source))
        else:
            im = Image.open(str(source))

        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass

        # Ensure RGB mode with white background for RGBA/palette images
        if im.mode == "RGBA":
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg.convert("RGB")
        elif im.mode != "RGB":
            im = im.convert("RGB")

        # 2. Float rotation with pure white fill
        rotation = float(trans.get("rotation", 0)) % 360.0
        if rotation != 0.0:
            # Pillow rotates counter-clockwise for positive angles
            angle = (360.0 - rotation) % 360.0
            im = im.rotate(
                angle,
                expand=True,
                resample=Image.Resampling.BICUBIC,
                fillcolor=(255, 255, 255),
            )

        # 3. Clamped relative crop (0.0 to 1.0)
        crop = trans.get("crop")
        if crop and isinstance(crop, dict):
            w, h = im.size
            cx = max(0, min(w - 1, int(float(crop.get("x", 0.0)) * w)))
            cy = max(0, min(h - 1, int(float(crop.get("y", 0.0)) * h)))
            cw = max(1, min(w - cx, int(float(crop.get("w", 1.0)) * w)))
            ch = max(1, min(h - cy, int(float(crop.get("h", 1.0)) * h)))
            if cw >= 10 and ch >= 10:
                im = im.crop((cx, cy, cx + cw, cy + ch))

        # 4. Apply all 8 studio filters
        filters = trans.get("filters", {})
        if filters:
            im = cls._apply_filters(im, filters)

        # 5. Output encoding
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
        rendered_bytes = buf.getvalue()
        render_hash = cls.calculate_hash(rendered_bytes)

        return rendered_bytes, render_hash, im.width, im.height

    @classmethod
    def _apply_filters(cls, im: Image.Image, filters: Dict[str, Any]) -> Image.Image:
        """Apply 8 synchronized photo filters."""
        # 1. Whiten (tone lift towards white)
        whiten = float(filters.get("whiten", 0))
        if whiten != 0:
            factor = 1.0 + (whiten / 200.0)
            im = ImageEnhance.Brightness(im).enhance(max(0.2, factor))

        # 2. Brightness
        bright = float(filters.get("brightness", 0))
        if bright != 0:
            factor = 1.0 + (bright / 100.0)
            im = ImageEnhance.Brightness(im).enhance(max(0.1, factor))

        # 3. Contrast
        contrast = float(filters.get("contrast", 0))
        if contrast != 0:
            factor = 1.0 + (contrast / 100.0)
            im = ImageEnhance.Contrast(im).enhance(max(0.1, factor))

        # 4. Saturation
        sat = float(filters.get("saturation", 0))
        if sat != 0:
            factor = 1.0 + (sat / 100.0)
            im = ImageEnhance.Color(im).enhance(max(0.0, factor))

        # 5. Sharpness
        sharpness = float(filters.get("sharpness", 0))
        if sharpness > 0:
            percent = 100 + int(sharpness * 1.5)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=percent, threshold=3))

        # 6. Warmth / Temperature
        warmth = float(filters.get("warmth", 0))
        # 7. Highlights
        highlights = float(filters.get("highlights", 0))
        # 8. Shadows
        shadows = float(filters.get("shadows", 0))

        if warmth != 0 or highlights != 0 or shadows != 0:
            im = cls._apply_curve_adjustments(im, warmth, highlights, shadows)

        return im

    @staticmethod
    def _apply_curve_adjustments(
        im: Image.Image, warmth: float, highlights: float, shadows: float
    ) -> Image.Image:
        """Color curves for warmth, highlights, and shadows using NumPy LUT."""
        arr = np.array(im, dtype=np.float32)

        # Warmth: boost red and reduce blue
        if warmth != 0:
            shift = (warmth / 100.0) * 20.0
            arr[:, :, 0] = np.clip(arr[:, :, 0] + shift, 0, 255)  # Red
            arr[:, :, 2] = np.clip(arr[:, :, 2] - shift, 0, 255)  # Blue

        # Highlights and Shadows adjustment
        if highlights != 0 or shadows != 0:
            # Normalized luminance
            norm = arr / 255.0
            if highlights != 0:
                h_shift = (highlights / 100.0) * 0.25
                high_mask = norm ** 2
                arr += h_shift * high_mask * 255.0
            if shadows != 0:
                s_shift = (shadows / 100.0) * 0.25
                low_mask = (1.0 - norm) ** 2
                arr += s_shift * low_mask * 255.0
            arr = np.clip(arr, 0, 255)

        return Image.fromarray(arr.astype(np.uint8))

