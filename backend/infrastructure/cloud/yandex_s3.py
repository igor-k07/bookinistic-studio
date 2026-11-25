"""Two-tier Yandex S3 Object Storage adapter.

Implements ICloudStorage port with zero monkey-patching:
- Tier 1: Proactive staging upload (staging/{store_id}/{asset_id}_{sha8}.jpg)
- Tier 2: Instant server-side CopyObject promotion to canonical book folder
- Shared static card (static/99_card.jpg)
- Ozon 14-photo cap with 99_card.jpg strictly placed last
- Parallel operations via ThreadPoolExecutor
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, List, Optional, Sequence, Set, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.config.settings import AppSettings
from backend.domain.exceptions import StorageError
from backend.domain.ports import ICloudStorage

logger = logging.getLogger("bookinistic.cloud.s3")


def sanitize_s3_key(key: str) -> str:
    """Sanitize S3 key ensuring clean ASCII, valid path segments, and no duplicate slashes."""
    clean = re.sub(r"/+", "/", key.strip("/"))
    parts = []
    for part in clean.split("/"):
        sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", part)
        parts.append(sanitized)
    return "/".join(parts)


class YandexS3Adapter(ICloudStorage):
    """Adapter for Yandex Cloud S3 object storage."""

    def __init__(
        self,
        bucket: str = "another-piter-books1",
        key_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        endpoint_url: str = "https://storage.yandexcloud.net",
        region_name: str = "ru-central1",
        client: Optional[Any] = None,
        s3_client: Optional[Any] = None,
        max_workers: int = 6,
    ) -> None:
        self.bucket = bucket.strip()
        self.key_id = key_id.strip() if key_id else None
        self.secret_key = secret_key.strip() if secret_key else None
        self.endpoint_url = endpoint_url.strip().rstrip("/")
        self.region_name = region_name.strip()
        self.max_workers = max(1, max_workers)

        self._client = s3_client if s3_client is not None else client
        self._client_lock = threading.Lock()
        self._lock = threading.Lock()

        # In-memory deduplication caches
        self._staging_cache: Set[Tuple[str, str]] = set()  # (key, sha8)
        self._promoted_cache: Set[Tuple[str, str]] = set()  # (dest_key, sha8)
        self._static_card_ensured: bool = False

    @property
    def is_configured(self) -> bool:
        """Check if S3 adapter has valid credentials or an injected client."""
        if self._client is not None:
            return True
        return bool(self.key_id and self.secret_key and self.bucket)

    @classmethod
    def from_settings(
        cls, settings: AppSettings, client: Optional[Any] = None, max_workers: int = 6
    ) -> "YandexS3Adapter":
        """Factory creating adapter from resolved AppSettings."""
        cfg = settings.get_effective_s3_config()
        if not cfg:
            return cls(
                bucket=settings.s3_bucket or "another-piter-books1",
                endpoint_url=settings.s3_endpoint_url,
                region_name=settings.s3_region_name,
                client=client,
                max_workers=max_workers,
            )
        return cls(
            bucket=cfg.get("bucket", "another-piter-books1"),
            key_id=cfg.get("key_id"),
            secret_key=cfg.get("secret_key"),
            endpoint_url=cfg.get("endpoint_url", "https://storage.yandexcloud.net"),
            region_name=cfg.get("region_name", "ru-central1"),
            client=client,
            max_workers=max_workers,
        )

    def _get_client(self) -> Any:
        """Obtain thread-safe boto3 S3 client with zero monkey-patching."""
        if self._client is not None:
            return self._client

        with self._client_lock:
            if self._client is not None:
                return self._client

            if not self.key_id or not self.secret_key:
                raise StorageError("Yandex S3 credentials (key_id / secret_key) not configured")

            session = boto3.session.Session()
            self._client = session.client(
                service_name="s3",
                endpoint_url=self.endpoint_url,
                region_name=self.region_name,
                aws_access_key_id=self.key_id,
                aws_secret_access_key=self.secret_key,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    connect_timeout=5,
                    read_timeout=15,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
            return self._client

    def _to_clean_ascii_url(self, key: str) -> str:
        """Generate clean, ASCII-safe public HTTPS URL."""
        clean_key = sanitize_s3_key(key).lstrip("/")
        return f"{self.endpoint_url}/{self.bucket}/{clean_key}"

    def _extract_key_from_url_or_key(self, source: str) -> str:
        """Extract bucket-relative S3 key from URL or plain key."""
        clean = source.strip()
        if clean.startswith("http://") or clean.startswith("https://"):
            bucket_token = f"/{self.bucket}/"
            if bucket_token in clean:
                return clean.split(bucket_token, 1)[1].lstrip("/")
            parts = clean.split("/", 3)
            if len(parts) >= 4:
                return parts[3].lstrip("/")
        return clean.lstrip("/")

    def upload_staging(
        self, store_id: str, asset_id: str, render_hash: str, data: bytes
    ) -> str:
        """Proactively upload rendered photo bytes to staging tier with dedup."""
        if not data:
            raise StorageError("Cannot upload empty data")

        sha8 = (
            render_hash[:8] if render_hash else hashlib.sha256(data).hexdigest()[:8]
        ).lower()
        key = sanitize_s3_key(f"staging/{store_id}/{asset_id}_{sha8}.jpg")

        with self._lock:
            if (key, sha8) in self._staging_cache:
                return self._to_clean_ascii_url(key)

        client = self._get_client()

        # Check remote existence for deduplication
        exists = False
        try:
            client.head_object(Bucket=self.bucket, Key=key)
            exists = True
        except ClientError as e:
            err_code = str(e.response.get("Error", {}).get("Code", ""))
            if err_code not in ("404", "NoSuchKey", "NotFound"):
                logger.error("S3 head_object error on %s: %s", key, e)
                raise StorageError(f"S3 head_object failed: {e}") from e

        if not exists:
            try:
                client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data,
                    ContentType="image/jpeg",
                    CacheControl="public, max-age=86400",
                )
            except ClientError as e:
                logger.error("Failed to upload staging asset %s: %s", key, e)
                raise StorageError(f"S3 staging upload failed: {e}") from e

        with self._lock:
            self._staging_cache.add((key, sha8))

        return self._to_clean_ascii_url(key)

    def promote_to_book(
        self,
        store_id: str,
        article: str,
        canonical_name: str,
        staging_key: str,
        sha8: str,
    ) -> str:
        """Promote staging asset to canonical book folder via server-side CopyObject (~30ms)."""
        clean_canonical = canonical_name.strip().lstrip("/")
        stem = Path(clean_canonical).stem
        clean_sha8 = (sha8[:8] if sha8 else "00000000").lower()

        # Archive info pages strictly under archive/ subfolder
        is_archive = clean_canonical.startswith("archive/") or stem.startswith("info_page")
        if is_archive:
            raw_dest = f"books/{store_id}/{article}/archive/{stem}_{clean_sha8}.jpg"
        else:
            raw_dest = f"books/{store_id}/{article}/{stem}_{clean_sha8}.jpg"
        dest_key = sanitize_s3_key(raw_dest)

        with self._lock:
            if (dest_key, clean_sha8) in self._promoted_cache:
                return self._to_clean_ascii_url(dest_key)

        source_key = sanitize_s3_key(self._extract_key_from_url_or_key(staging_key))
        client = self._get_client()

        try:
            client.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": source_key},
                Key=dest_key,
                CacheControl="public, max-age=31536000, immutable",
            )
        except ClientError as e:
            logger.error(
                "Failed to copy %s to %s in bucket %s: %s", source_key, dest_key, self.bucket, e
            )
            raise StorageError(f"S3 copy_object failed: {e}") from e

        with self._lock:
            self._promoted_cache.add((dest_key, clean_sha8))

        return self._to_clean_ascii_url(dest_key)

    def ensure_static_card(
        self,
        card_data: Optional[bytes] = None,
        card_path: Optional[str | Path] = None,
    ) -> str:
        """Ensure the shared promo card (static/99_card.jpg) exists in S3."""
        if self._static_card_ensured:
            return self.get_static_card_url()

        key = "static/99_card.jpg"
        client = self._get_client()

        exists = False
        try:
            client.head_object(Bucket=self.bucket, Key=key)
            exists = True
        except ClientError as e:
            err_code = str(e.response.get("Error", {}).get("Code", ""))
            if err_code not in ("404", "NoSuchKey", "NotFound"):
                raise StorageError(f"Failed to check static card: {e}") from e

        if not exists:
            data_to_upload: Optional[bytes] = card_data
            if data_to_upload is None:
                candidates = [
                    Path(card_path) if card_path else None,
                    Path("templates/card.png"),
                    Path("templates/card.jpg"),
                    Path("templates/static/card.png"),
                ]
                for candidate in candidates:
                    if candidate and candidate.is_file():
                        try:
                            data_to_upload = candidate.read_bytes()
                            break
                        except OSError:
                            pass

            if not data_to_upload:
                # 1x1 white JPEG fallback
                data_to_upload = (
                    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
                    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
                    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
                    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
                    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00"
                    b"\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00"
                    b"\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00"
                    b"\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
                )

            try:
                client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data_to_upload,
                    ContentType="image/jpeg",
                    CacheControl="public, max-age=31536000, immutable",
                )
            except ClientError as e:
                logger.error("Failed to upload static card %s: %s", key, e)
                raise StorageError(f"Failed to upload static card: {e}") from e

        self._static_card_ensured = True
        return self.get_static_card_url()

    def get_static_card_url(self) -> str:
        """Return canonical URL for the shared static card."""
        return self._to_clean_ascii_url("static/99_card.jpg")

    def format_ozon_photo_urls(
        self,
        main_photo_url: str,
        additional_photo_urls: Sequence[str],
        include_static_card: bool = True,
    ) -> Tuple[str, str]:
        """
        Enforce Ozon 14-photo limit on additional photos and place 99_card.jpg strictly last.

        Returns:
            (main_photo_url, space_separated_additional_urls)
        """
        card_url = self.get_static_card_url()
        add_photos = [u for u in additional_photo_urls if "99_card" not in u and u != card_url]

        if include_static_card:
            if len(add_photos) >= 14:
                final_add = add_photos[:13] + [card_url]
            else:
                final_add = add_photos + [card_url]
        else:
            final_add = add_photos[:14]

        return main_photo_url, " ".join(final_add)

    def prepare_ozon_photos(
        self,
        main_photo_url: Optional[str],
        additional_photo_urls: Sequence[str],
        include_card: bool = True,
    ) -> Tuple[Optional[str], List[str]]:
        """Return Ozon photo URLs as tuple of (main_photo_url, list_of_additional_urls)."""
        main_res, add_str = self.format_ozon_photo_urls(
            main_photo_url or "", additional_photo_urls, include_static_card=include_card
        )
        return (main_res if main_photo_url else None, add_str.split() if add_str else [])

    def batch_upload_staging(
        self, items: Sequence[Tuple[str, str, str, bytes]]
    ) -> List[str]:
        """Upload batch of staging items in parallel using ThreadPoolExecutor."""
        if not items:
            return []

        def _worker(item: Tuple[str, str, str, bytes]) -> str:
            store_id, asset_id, render_hash, data = item
            return self.upload_staging(store_id, asset_id, render_hash, data)

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(items))) as pool:
            return list(pool.map(_worker, items))

    def batch_promote_to_book(
        self, items: Sequence[Tuple[str, str, str, str, str]]
    ) -> List[str]:
        """Promote batch of items via server-side CopyObject in parallel."""
        if not items:
            return []

        def _worker(item: Tuple[str, str, str, str, str]) -> str:
            store_id, article, canonical_name, staging_key, sha8 = item
            return self.promote_to_book(store_id, article, canonical_name, staging_key, sha8)

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(items))) as pool:
            return list(pool.map(_worker, items))
