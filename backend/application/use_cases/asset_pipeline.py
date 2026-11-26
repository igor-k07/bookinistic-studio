"""Asset Pipeline Use Case.

Handles binary uploads, non-destructive transformations with Optimistic Locking,
real ImageRenderPipeline rendering, selective/forced rembg processing, and S3 staging.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Dict, Optional

from backend.domain.enums import AssetStatus
from backend.domain.exceptions import ConcurrencyError, EntityNotFoundError
from backend.domain.models import Asset
from backend.domain.ports import IAssetRepository, ICloudStorage, IEventBroker, IMediaStorage
from backend.domain.rules import normalize_photo_role

logger = logging.getLogger(__name__)


class AssetPipelineUseCase:
    """Use case coordinating asset lifecycle from upload to S3 staging."""

    def __init__(
        self,
        asset_repo: IAssetRepository,
        media_storage: IMediaStorage,
        cloud_storage: Optional[ICloudStorage] = None,
        event_broker: Optional[IEventBroker] = None,
        render_pipeline: Optional[Any] = None,
        rembg_processor: Optional[Any] = None,
    ) -> None:
        self.asset_repo = asset_repo
        self.media_storage = media_storage
        self.cloud_storage = cloud_storage
        self.event_broker = event_broker
        self.render_pipeline = render_pipeline
        self.rembg_processor = rembg_processor

    def create_asset(
        self,
        book_article: Optional[str],
        raw_data: bytes,
        original_filename: str = "",
        slot: Optional[str] = None,
    ) -> Asset:
        """Create a new asset from uploaded binary data."""
        asset_id = uuid.uuid4().hex[:12]
        file_hash = hashlib.sha256(raw_data).hexdigest()

        # Slot normalization: explicit slot or explicit semantic filename hint; generic camera names stay unassigned in pool
        if slot:
            normalized_slot: Optional[str] = normalize_photo_role(slot)
        elif original_filename:
            inferred = normalize_photo_role(original_filename)
            normalized_slot = (
                inferred
                if inferred in ("cover_front", "cover_back", "info_pages", "mantra_defects")
                else None
            )
        else:
            normalized_slot = None

        # Save raw binary to local media vault
        rel_path = f"assets/{asset_id}_orig.jpg"
        saved_path = self.media_storage.save_file(rel_path, raw_data)

        asset = Asset(
            id=asset_id,
            book_article=book_article,
            slot=normalized_slot,
            status=AssetStatus.UPLOADED,
            original_path=saved_path,
            preview_path=saved_path,
            render_hash=file_hash,
            file_size_bytes=len(raw_data),
            version=1,
        )
        self.asset_repo.save(asset)
        self._notify_event("asset.updated", {"asset_id": asset_id, "status": asset.status.value})
        logger.info("Created asset %s for book %s", asset_id, book_article)
        return asset

    def apply_transform(
        self,
        asset_id: str,
        transformations: Dict[str, Any],
        expected_version: int,
    ) -> Asset:
        """Apply non-destructive transformations with Optimistic Locking and real Pillow render."""
        asset = self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise EntityNotFoundError(f"Asset {asset_id} not found")

        if asset.version != expected_version:
            raise ConcurrencyError(
                f"Asset {asset_id} version mismatch: expected {expected_version}, found {asset.version}"
            )

        asset.transformations = dict(transformations)
        tx_repr = str(sorted(transformations.items()))
        new_hash = hashlib.sha256(f"{asset.render_hash}:{tx_repr}".encode("utf-8")).hexdigest()

        # Render actual preview image if render_pipeline is wired
        if self.render_pipeline is not None:
            try:
                use_ai = bool(transformations.get("use_ai_white") and asset.ai_white_path)
                src_path = asset.ai_white_path if use_ai and asset.ai_white_path else asset.original_path
                src_bytes = self.media_storage.read_file(src_path)
                rendered_bytes, render_sha, w, h = self.render_pipeline.render(
                    src_bytes, transformations
                )
                preview_rel = f"assets/{asset_id}_preview.jpg"
                saved_preview = self.media_storage.save_file(preview_rel, rendered_bytes)
                asset.preview_path = saved_preview
                asset.width = w
                asset.height = h
                new_hash = render_sha
            except Exception as e:
                logger.warning("Render pipeline failed for %s, keeping previous preview: %s", asset_id, e)

        asset.render_hash = new_hash
        asset.status = AssetStatus.READY
        self.asset_repo.save(asset)
        self._notify_event(
            "asset.updated",
            {"asset_id": asset_id, "status": asset.status.value, "version": asset.version},
        )
        return asset

    def assign_slot(
        self,
        asset_id: str,
        slot: Optional[str],
        slot_order: int = 0,
        book_article: Optional[str] = None,
    ) -> Asset:
        """Assign or unassign an asset to a semantic photo slot."""
        asset = self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise EntityNotFoundError(f"Asset {asset_id} not found")

        asset.slot = normalize_photo_role(slot) if slot else None
        asset.slot_order = slot_order
        if book_article is not None:
            asset.book_article = book_article if book_article else None
        elif slot is None:
            asset.book_article = None

        self.asset_repo.save(asset)
        self._notify_event(
            "asset.updated",
            {
                "asset_id": asset_id,
                "slot": asset.slot,
                "slot_order": slot_order,
                "version": asset.version,
            },
        )
        return asset

    def trigger_rembg(self, asset_id: str, force: bool = False) -> Asset:
        """Trigger AI background removal for book covers (or any photo when force=True)."""
        asset = self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise EntityNotFoundError(f"Asset {asset_id} not found")

        is_cover = bool(asset.slot and ("cover" in asset.slot or asset.slot in ("01_cover_front", "cover_front")))
        if not force and not is_cover:
            logger.info("Asset %s (slot %s) is not a cover; skipping rembg", asset_id, asset.slot)
            return asset

        asset.status = AssetStatus.AI_PROCESSING
        self.asset_repo.save(asset)

        white_rel_path = f"assets/{asset_id}_white.jpg"
        raw_data = self.media_storage.read_file(asset.original_path)
        processed_data = raw_data
        if self.rembg_processor is not None:
            try:
                processed_data = self.rembg_processor.process_bytes(raw_data)
            except Exception as e:
                logger.warning("rembg failed for %s, falling back to original: %s", asset_id, e)

        saved_white = self.media_storage.save_file(white_rel_path, processed_data)
        asset.ai_white_path = saved_white
        asset.preview_path = saved_white
        asset.transformations = {**(asset.transformations or {}), "use_ai_white": True}
        asset.status = AssetStatus.READY
        self.asset_repo.save(asset)
        self._notify_event(
            "asset.updated",
            {"asset_id": asset_id, "status": asset.status.value, "version": asset.version},
        )
        return asset

    def upload_to_staging(self, asset_id: str, store_id: str, data: bytes) -> str:
        """Proactively upload rendered asset to S3 staging keyed by render_hash."""
        if not self.cloud_storage:
            raise RuntimeError("Cloud storage adapter is not configured")

        asset = self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise EntityNotFoundError(f"Asset {asset_id} not found")

        staging_url = self.cloud_storage.upload_staging(
            store_id=store_id,
            asset_id=asset_id,
            render_hash=asset.render_hash,
            data=data,
        )
        asset.s3_staging_url = staging_url
        asset.s3_uploaded_hash = asset.render_hash
        self.asset_repo.save(asset)
        self._notify_event("asset.updated", {"asset_id": asset_id, "s3_staging_url": staging_url})
        return staging_url

    def _notify_event(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.event_broker:
            try:
                self.event_broker.publish(event_type, data)
            except Exception as e:
                logger.warning("Event dispatch failed for %s: %s", event_type, e)
