"""Yandex S3 Object Storage adapter implementing two-tier cloud storage.

Architectural Guarantees:
- Pure boto3 client without any monkey-patching or socket manipulation.
- Two-tier storage flow:
  1. Staging: proactive rendered photo upload (staging/{store_id}/{asset_id}_{sha8}.jpg).
  2. Final promotion: server-side S3 copy_object (~30ms, 0 client upload bandwidth).
- Deduplication: checks existing render_hash to prevent redundant byte transfers.
- Single shared static warning card (static/99_card.jpg).
- Ozon 14-photo cap with static card placed last.
- Strict ASCII-clean URL and key formatting.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.config.settings import AppSettings
from backend.domain.exceptions import StorageError
from backend.domain.ports import ICloudStorage

logger = logging.getLogger(__name__)

SAFE_ASCII_PATTERN = re.compile(r"[^a-zA-Z0-9_\-\./]")


def sanitize_s3_key(key: str) -> str:
    """Ensure key contains only ASCII alphanumeric, dash, underscore, dot, and slash."""
    cleaned = SAFE_ASCII_PATTERN.sub("_", key.strip())
    # Collapse multiple consecutive slashes
    return re.sub(r"/+", "/", cleaned).lstrip("/")


class YandexS3Adapter(ICloudStorage):
    """Two-tier Yandex Cloud Object Storage adapter."""

    def __init__(
        self,
        bucket: Optional[str] = None,
        key_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        endpoint_url: str = "https://storage.yandexcloud.net",
        region_name: str = "ru-central1",
        s3_client: Optional[Any] = None,
        settings: Optional[AppSettings] = None,
        max_workers: int = 6,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.region_name = region_name
        self.max_workers = max(1, max_workers)

        if s3_client is not None:
            self._client = s3_client
            self.bucket = bucket or "bookinistic-storage"
            return

        cfg: Optional[Dict[str, str]] = None
        if bucket and key_id and secret_key:
            cfg = {
                "bucket": bucket,
                "key_id": key_id,
                "secret_key": secret_key,
                "endpoint_url": self.endpoint_url,
                "region_name": self.region_name,
            }
        else:
            app_settings = settings or AppSettings()
            cfg = app_settings.get_effective_s3_config()

        if cfg:
            self.bucket = cfg["bucket"]
            self.endpoint_url = cfg.get("endpoint_url", self.endpoint_url).rstrip("/")
            self.region_name = cfg.get("region_name", self.region_name)
            session = boto3.session.Session()
            self._client = session.client(
                service_name="s3",
                endpoint_url=self.endpoint_url,
                region_name=self.region_name,
                aws_access_key_id=cfg["key_id"],
                aws_secret_access_key=cfg["secret_key"],
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    connect_timeout=5,
                    read_timeout=15,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        else:
            self.bucket = bucket or ""
            self._client = None
            logger.warning("Yandex S3 adapter initialized without valid credentials")

    @property
    def is_configured(self) -> bool:
        """Check if S3 client and bucket are configured."""
        return self._client is not None and bool(self.bucket)

    def _require_client(self) -> Any:
        if not self.is_configured:
            raise StorageError("Yandex S3 adapter is not configured with credentials")
        return self._client

    def get_public_url(self, key: str) -> str:
        """Construct standard public HTTPS URL for an S3 key."""
        clean_key = sanitize_s3_key(key)
        return f"{self.endpoint_url}/{self.bucket}/{clean_key}"

    def extract_key_from_url_or_key(self, path_or_url: str) -> str:
        """Extract relative S3 key from either a full URL or a relative key string."""
        if path_or_url.startswith(("http://", "https://")):
            parsed = urlparse(path_or_url)
            path = parsed.path.lstrip("/")
            bucket_prefix = f"{self.bucket}/"
            if path.startswith(bucket_prefix):
                return sanitize_s3_key(path[len(bucket_prefix) :])
            return sanitize_s3_key(path)
        return sanitize_s3_key(path_or_url)

    def object_exists(self, key: str) -> bool:
        """Check whether an object exists in S3 via head_object."""
        client = self._require_client()
        clean_key = sanitize_s3_key(key)
        try:
            client.head_object(Bucket=self.bucket, Key=clean_key)
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            logger.warning("Error checking object existence for %s: %s", clean_key, e)
            return False
        except Exception as e:
            logger.warning("Unexpected error during head_object for %s: %s", clean_key, e)
            return False

    def upload_staging(
        self,
        store_id: str,
        asset_id: str,
        render_hash: str,
        data: bytes,
        content_type: str = "image/jpeg",
        force: bool = False,
    ) -> str:
        """Upload rendered asset to staging tier with content-hash deduplication.

        Path: staging/{store_id}/{asset_id}_{sha8}.jpg
        """
        client = self._require_client()
        if not data:
            raise StorageError(f"Cannot upload empty data for asset {asset_id}")

        sha8 = render_hash[:8] if len(render_hash) >= 8 else render_hash
        clean_store = sanitize_s3_key(store_id)
        clean_asset = sanitize_s3_key(asset_id)
        key = f"staging/{clean_store}/{clean_asset}_{sha8}.jpg"

        if not force and self.object_exists(key):
            logger.debug("Staging asset already exists (dedup hit): %s", key)
            return self.get_public_url(key)

        try:
            client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                CacheControl="public, max-age=86400",
            )
            logger.info("Uploaded to S3 staging: %s (%d bytes)", key, len(data))
            return self.get_public_url(key)
        except Exception as e:
            logger.error("Failed uploading to S3 staging %s: %s", key, e)
            raise StorageError(f"Failed uploading {key} to S3 staging: {e}") from e

    def promote_to_book(
        self,
        store_id: str,
        article: str,
        canonical_name: str,
        staging_key: str,
        sha8: str,
    ) -> str:
        """Promote staging asset to canonical book tier via server-side copy_object.

        Path: books/{store_id}/{article}/{stem}_{sha8}.jpg
        Zero client upload bandwidth, ~30ms latency.
        """
        client = self._require_client()
        src_key = self.extract_key_from_url_or_key(staging_key)
        stem = Path(canonical_name).stem
        clean_store = sanitize_s3_key(store_id)
        clean_article = sanitize_s3_key(article)
        clean_stem = sanitize_s3_key(stem)
        dest_key = f"books/{clean_store}/{clean_article}/{clean_stem}_{sha8}.jpg"

        try:
            client.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": src_key},
                Key=dest_key,
                CacheControl="public, max-age=31536000, immutable",
            )
            logger.info("Promoted S3 asset: %s -> %s", src_key, dest_key)
            return self.get_public_url(dest_key)
        except Exception as e:
            logger.error("Failed server-side promote %s -> %s: %s", src_key, dest_key, e)
            raise StorageError(
                f"Failed promoting {src_key} to {dest_key} in S3: {e}"
            ) from e

    def get_static_card_url(self) -> str:
        """Return public URL for the shared static warning card."""
        return self.get_public_url("static/99_card.jpg")

    def ensure_static_card(
        self,
        card_data: Optional[bytes] = None,
        template_candidates: Optional[List[Path]] = None,
        force: bool = False,
    ) -> str:
        """Ensure single shared static warning card (static/99_card.jpg) exists in S3."""
        key = "static/99_card.jpg"
        if not force and self.object_exists(key):
            return self.get_public_url(key)

        data = card_data
        if not data:
            candidates = template_candidates or [
                Path("templates/card.png"),
                Path("storage/card.png"),
                Path("card.png"),
            ]
            for path in candidates:
                if path.is_file() and path.stat().st_size > 0:
                    try:
                        data = path.read_bytes()
                        break
                    except OSError:
                        pass

        if not data:
            logger.warning(
                "Static card image not found on disk; skipping upload, returning expected URL"
            )
            return self.get_public_url(key)

        client = self._require_client()
        try:
            client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType="image/jpeg",
                CacheControl="public, max-age=31536000, immutable",
            )
            logger.info("Uploaded static warning card to S3: %s", key)
            return self.get_public_url(key)
        except Exception as e:
            logger.error("Failed uploading static card to S3: %s", e)
            raise StorageError(f"Failed to ensure static card in S3: {e}") from e

    def batch_upload_staging(
        self, items: List[Tuple[str, str, str, bytes]]
    ) -> List[str]:
        """Upload multiple items to staging in parallel with max_workers.

        Items format: List of (store_id, asset_id, render_hash, data).
        Returns URLs preserving original input order.
        """
        if not items:
            return []

        results: List[Optional[str]] = [None] * len(items)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self.upload_staging,
                    item[0],
                    item[1],
                    item[2],
                    item[3],
                ): idx
                for idx, item in enumerate(items)
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                results[idx] = fut.result()

        return [res for res in results if res is not None]

    def batch_promote_to_book(
        self, items: List[Tuple[str, str, str, str, str]]
    ) -> List[str]:
        """Promote multiple staging keys in parallel with max_workers.

        Items format: List of (store_id, article, canonical_name, staging_key, sha8).
        Returns URLs preserving original input order.
        """
        if not items:
            return []

        results: List[Optional[str]] = [None] * len(items)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self.promote_to_book,
                    item[0],
                    item[1],
                    item[2],
                    item[3],
                    item[4],
                ): idx
                for idx, item in enumerate(items)
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                results[idx] = fut.result()

        return [res for res in results if res is not None]

    def format_ozon_photo_urls(
        self,
        main_url: Optional[str],
        add_urls: List[str],
        include_static_card: bool = True,
    ) -> Tuple[Optional[str], str]:
        """Format and enforce Ozon marketplace photo constraints.

        Constraints:
        - Maximum 14 additional photos.
        - Shared static card (99_card.jpg) strictly appended as the LAST photo.
        - Returns (main_url, "url1 url2 ... urlN").
        """
        card_url = self.get_static_card_url() if include_static_card else None

        # Filter out card_url from intermediate list to avoid duplication
        clean_adds = [u for u in add_urls if u and u != card_url]

        if card_url:
            if len(clean_adds) >= 14:
                final_adds = clean_adds[:13] + [card_url]
            else:
                final_adds = clean_adds + [card_url]
        else:
            final_adds = clean_adds[:14]

        return main_url, " ".join(final_adds)
