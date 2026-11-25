"""Media processing infrastructure for Bookinistic Studio 2.0 (Photo Engine V3)."""

from backend.infrastructure.media.barcode_scanner import BarcodeScanner
from backend.infrastructure.media.rembg_processor import RembgImageProcessor
from backend.infrastructure.media.render_pipeline import ImageRenderPipeline
from backend.infrastructure.media.vault_store import VaultStore

__all__ = [
    "BarcodeScanner",
    "ImageRenderPipeline",
    "RembgImageProcessor",
    "VaultStore",
]
