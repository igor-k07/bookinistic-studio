"""Local vault storage for book photo archives and Ozon ZIP packages.

Stores strictly under {vault_dir}/{article}/ (no mutable title in path).
Atomic manifest.json (no Base64) and streaming Ozon ZIP generation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple, Union

from backend.config.store_context import safe_path

logger = logging.getLogger(__name__)

# Pattern to identify info pages that must be excluded from Ozon export
INFO_PAGE_PATTERN = re.compile(r"^info_page_.*", re.IGNORECASE)


class VaultStore:
    """Manages local physical book archive directories and Ozon ZIP exports."""

    def __init__(self, vault_dir: Union[str, Path]) -> None:
        self.vault_dir = Path(vault_dir).resolve()
        self.vault_dir.mkdir(parents=True, exist_ok=True)

    def get_book_dir(self, article: str) -> Path:
        """Resolve book folder path strictly by article (immune to title changes)."""
        clean_art = str(article or "").strip().upper()
        if not clean_art:
            raise ValueError("Article cannot be empty")
        return safe_path(self.vault_dir, clean_art)

    def save_book_vault(
        self,
        article: str,
        book_metadata: Dict[str, Any],
        photos: List[Tuple[str, bytes, Optional[bytes]]],
    ) -> Path:
        """Save rendered photos, raw originals, and atomic manifest.json.

        photos: list of (canonical_filename, rendered_bytes, optional_raw_bytes)
        """
        book_dir = self.get_book_dir(article)
        book_dir.mkdir(parents=True, exist_ok=True)
        raw_dir = book_dir / "raw_sources"
        raw_dir.mkdir(parents=True, exist_ok=True)

        manifest_files = []

        for filename, rendered_bytes, raw_bytes in photos:
            clean_name = Path(filename).name
            target_path = book_dir / clean_name
            target_path.write_bytes(rendered_bytes)

            file_hash = hashlib.sha256(rendered_bytes).hexdigest()
            manifest_files.append({
                "filename": clean_name,
                "size_bytes": len(rendered_bytes),
                "sha256": file_hash,
                "is_info_page": bool(INFO_PAGE_PATTERN.match(clean_name)),
            })

            if raw_bytes:
                (raw_dir / clean_name).write_bytes(raw_bytes)

        # Sanitize metadata: remove any accidental Base64 data
        clean_meta = self._sanitize_metadata(book_metadata)
        clean_meta["article"] = article
        clean_meta["files"] = manifest_files

        # Atomic manifest.json write
        manifest_path = book_dir / "manifest.json"
        with tempfile.NamedTemporaryFile(dir=book_dir, suffix=".tmp", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp_path.write_text(json.dumps(clean_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(manifest_path)
        logger.info("Successfully updated vault archive for %s", article)
        return book_dir

    def save_file(self, rel_path: str, data: bytes) -> str:
        """Save a file relative to vault_dir conforming to IMediaStorage."""
        target = safe_path(self.vault_dir, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return str(target)

    def read_file(self, rel_path: str) -> bytes:
        """Read a file relative to vault_dir conforming to IMediaStorage."""
        target = safe_path(self.vault_dir, rel_path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {rel_path}")
        return target.read_bytes()

    def delete_file(self, rel_path: str) -> bool:
        """Delete a file relative to vault_dir conforming to IMediaStorage."""
        try:
            target = safe_path(self.vault_dir, rel_path)
            if target.is_file():
                target.unlink()
                return True
            return False
        except Exception:
            return False

    def get_manifest(self, article: str) -> Optional[Dict[str, Any]]:
        """Read and return manifest.json for article if present."""
        book_dir = self.get_book_dir(article)
        manifest_path = book_dir / "manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError):
            return None

    def list_photos(self, article: str) -> List[Path]:
        """List all rendered photos in book folder (excluding raw_sources)."""
        book_dir = self.get_book_dir(article)
        if not book_dir.is_dir():
            return []
        photos = []
        for p in sorted(book_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                photos.append(p)
        return photos

    def create_ozon_zip(self, article: str, zip_output_path: Path) -> int:
        """Create streaming ZIP for Ozon seller upload.

        Invariant: Excludes info_page_* and raw_sources/.
        Returns number of files packed.
        """
        book_dir = self.get_book_dir(article)
        if not book_dir.is_dir():
            raise FileNotFoundError(f"Book directory {book_dir} not found")

        zip_output_path.parent.mkdir(parents=True, exist_ok=True)
        file_count = 0

        with zipfile.ZipFile(zip_output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(book_dir.iterdir()):
                if not p.is_file():
                    continue
                if p.name == "manifest.json" or INFO_PAGE_PATTERN.match(p.name):
                    continue
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    zf.write(p, arcname=p.name)
                    file_count += 1

        return file_count

    def stream_ozon_zip(self, article: str, output_stream: BinaryIO) -> int:
        """Stream Ozon ZIP directly into an open binary stream without full-RAM buffering."""
        book_dir = self.get_book_dir(article)
        if not book_dir.is_dir():
            raise FileNotFoundError(f"Book directory {book_dir} not found")

        file_count = 0
        with zipfile.ZipFile(output_stream, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(book_dir.iterdir()):
                if not p.is_file():
                    continue
                if p.name == "manifest.json" or INFO_PAGE_PATTERN.match(p.name):
                    continue
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    zf.write(p, arcname=p.name)
                    file_count += 1

        return file_count

    @staticmethod
    def _sanitize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
        """Strip Base64 strings or heavy binary payloads from metadata dictionary."""
        sanitized = {}
        for k, v in meta.items():
            if isinstance(v, str) and (v.startswith("data:image/") or len(v) > 5000):
                continue
            if isinstance(v, dict):
                sanitized[k] = VaultStore._sanitize_metadata(v)
            else:
                sanitized[k] = v
        return sanitized
