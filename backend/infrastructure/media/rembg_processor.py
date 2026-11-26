"""Rembg background removal and contour protection.

Thread-safe u2net singleton with OpenCV white-cover protection and direct PIL pipeline.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
import rembg
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)


class RembgImageProcessor:
    """Thread-safe background cutout processor with white-cover preservation."""

    _session: Optional[Any] = None
    _session_lock = threading.Lock()

    @classmethod
    def get_session(cls) -> Any:
        """Get or lazily initialize thread-safe u2net session singleton."""
        if cls._session is None:
            with cls._session_lock:
                if cls._session is None:
                    try:
                        cls._session = rembg.new_session("u2net")
                        logger.info("Initialized rembg u2net session.")
                    except Exception as e:
                        logger.error(f"Failed to initialize rembg session: {e}")
                        cls._session = False
        return cls._session if cls._session is not False else None

    @classmethod
    def protect_white_cover_mask(cls, alpha_mask: Image.Image, raw_rgb: Image.Image) -> Image.Image:
        """Protect white and light covers from holes punched by rembg."""
        try:
            mask_np = np.array(alpha_mask)
            mask_bin = (mask_np > 24).astype(np.uint8) * 255

            contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return alpha_mask

            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            h, w = mask_np.shape
            total_pixels = h * w

            if area < total_pixels * 0.05:
                return alpha_mask

            hull = cv2.convexHull(largest)
            hull_mask = np.zeros_like(mask_np)
            cv2.drawContours(hull_mask, [hull], -1, 255, thickness=-1)

            rgb_np = np.array(raw_rgb)
            book_region = rgb_np[hull_mask == 255]
            mean_brightness = float(np.mean(book_region)) if len(book_region) > 0 else 0

            inner_mask_sum = np.sum(mask_np[hull_mask == 255] > 24)
            hull_area = np.sum(hull_mask == 255)
            fill_ratio = inner_mask_sum / max(1, hull_area)

            # If cover is light or rembg has punched holes, restore interior
            if mean_brightness > 190 or fill_ratio < 0.88:
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
                hull_closed = cv2.morphologyEx(hull_mask, cv2.MORPH_CLOSE, kernel)
                combined = np.maximum(mask_np, hull_closed)
                return Image.fromarray(combined)

            return alpha_mask
        except Exception as e:
            logger.warning(f"Contour protection fallback: {e}")
            return alpha_mask

    @classmethod
    def process_white_background(
        cls,
        image: Image.Image,
        apply_contour_padding: bool = True,
    ) -> Tuple[Image.Image, Optional[Dict[str, float]]]:
        """Cut out background to pure white (#FFFFFF) and calculate auto-crop coordinates."""
        raw_rgb = image.convert("RGB")

        # Downscale for rembg processing if huge
        proc_img = raw_rgb.copy()
        if max(proc_img.size) > 1600:
            proc_img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)

        session = cls.get_session()
        if session:
            img_rgba = rembg.remove(proc_img, session=session, alpha_matting=False)
        else:
            img_rgba = rembg.remove(proc_img, alpha_matting=False)

        if not isinstance(img_rgba, Image.Image):
            img_rgba = Image.fromarray(img_rgba)

        img_rgba = img_rgba.convert("RGBA")
        alpha = img_rgba.split()[-1]

        # White cover protection
        alpha = cls.protect_white_cover_mask(alpha, proc_img)

        # Alpha threshold > 24 for noise-free bounding box
        alpha_np = np.array(alpha)
        alpha_clean = np.where(alpha_np > 24, alpha_np, 0).astype(np.uint8)
        alpha_img_clean = Image.fromarray(alpha_clean)
        bbox = alpha_img_clean.getbbox()

        # Composite onto pure white #FFFFFF
        bg = Image.new("RGBA", img_rgba.size, (255, 255, 255, 255))
        bg.paste(img_rgba, mask=alpha_img_clean)
        full_rgb = bg.convert("RGB")

        # Subtle sharpening
        try:
            full_rgb = full_rgb.filter(ImageFilter.UnsharpMask(radius=1.2, percent=115, threshold=3))
        except Exception:
            pass

        # Calculate safe auto-crop (+3.5% padding)
        crop_relative = None
        if bbox and apply_contour_padding:
            w_orig, h_orig = full_rgb.size
            left, upper, right, lower = bbox
            bw, bh = right - left, lower - upper
            if bw > 30 and bh > 30:
                pad_x = max(16, int(bw * 0.035))
                pad_y = max(16, int(bh * 0.035))
                c_left = max(0, left - pad_x)
                c_upper = max(0, upper - pad_y)
                c_right = min(w_orig, right + pad_x)
                c_lower = min(h_orig, lower + pad_y)

                crop_relative = {
                    "x": round(c_left / w_orig, 4),
                    "y": round(c_upper / h_orig, 4),
                    "w": round((c_right - c_left) / w_orig, 4),
                    "h": round((c_lower - c_upper) / h_orig, 4),
                }

        return full_rgb, crop_relative

    @classmethod
    def process_bytes(cls, raw_data: bytes, jpeg_quality: int = 92) -> bytes:
        """Convenience wrapper accepting JPEG/PNG bytes and returning white-background JPEG bytes."""
        import io

        im = Image.open(io.BytesIO(raw_data))
        processed, _ = cls.process_white_background(im)
        buf = io.BytesIO()
        processed.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
        return buf.getvalue()

