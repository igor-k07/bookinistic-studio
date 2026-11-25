"""Fast local barcode scanner for cover_back images.

Uses OpenCV BarcodeDetector to locate and extract EAN-13 and ISBN barcodes.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

import cv2
import numpy as np
from PIL import Image

from backend.domain.value_objects import Ean13, Isbn

logger = logging.getLogger(__name__)


class BarcodeScanner:
    """Local EAN-13 and ISBN scanner using OpenCV."""

    def __init__(self) -> None:
        self.detector: Optional[Any] = None
        try:
            self.detector = cv2.barcode.BarcodeDetector()
        except Exception as e:
            logger.warning(f"OpenCV BarcodeDetector unavailable: {e}")

    def scan_image(self, source: Union[str, Image.Image, np.ndarray]) -> Optional[str]:
        """Detect and decode barcode from image. Returns cleaned 13-digit code or None."""
        if self.detector is None:
            return None

        try:
            if isinstance(source, str):
                cv_img = cv2.imread(source)
            elif isinstance(source, Image.Image):
                cv_img = cv2.cvtColor(np.array(source.convert("RGB")), cv2.COLOR_RGB2BGR)
            elif isinstance(source, np.ndarray):
                cv_img = source
            else:
                return None

            if cv_img is None or cv_img.size == 0:
                return None

            # Detect barcodes safely handling return tuple variations
            res = self.detector.detectAndDecode(cv_img)
            if not res or not res[0]:
                return None

            decoded_info = res[1] if len(res) > 1 else None
            if decoded_info:
                for code in decoded_info:
                    clean = str(code).strip()
                    if clean and len(clean) == 13 and clean.isdigit():
                        if Ean13.validate_checksum(clean):
                            return clean

                    # Check for valid ISBN
                    isbn = Isbn.parse(clean)
                    if isbn and isbn.is_valid:
                        return isbn.clean_digits

            return None
        except Exception as e:
            logger.warning(f"Barcode scan failed: {e}")
            return None

