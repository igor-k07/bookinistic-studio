"""Cleanup Storage Use Case.

Transactional storage garbage collection:
- Identifies ARCHIVED assets that have verified cloud backups (s3_final_url present).
- Strictly protects assets linked to active workspace_tabs (never deletes files in active editing).
- Transactionally deletes local temporary files (original, preview, white-cover intermediates).
- Removes cleaned asset records from SQLite.
- Dispatches SSE event on completion.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.domain.enums import AssetStatus
from backend.domain.ports import (
    IAssetRepository,
    IBookRepository,
    IEventBroker,
    IMediaStorage,
    IUnitOfWork,
)

logger = logging.getLogger(__name__)


class CleanupStorageUseCase:
    """Use case freeing local disk space by pruning safely archived temporary files."""

    def __init__(
        self,
        uow: IUnitOfWork,
        asset_repo: IAssetRepository,
        book_repo: IBookRepository,
        media_storage: IMediaStorage,
        event_broker: Optional[IEventBroker] = None,
    ) -> None:
        self.uow = uow
        self.asset_repo = asset_repo
        self.book_repo = book_repo
        self.media_storage = media_storage
        self.event_broker = event_broker

    def execute(self, store_id: str, dry_run: bool = False) -> Dict[str, Any]:
        """Perform transactional disk cleanup."""
        # 1. Collect articles currently open in active workspace tabs
        active_tabs = self.book_repo.list_tabs()
        active_articles = {
            tab.book_article.strip().upper() for tab in active_tabs if tab.book_article
        }

        # 2. Find eligible ARCHIVED assets
        archived_assets = self.asset_repo.list_by_status(AssetStatus.ARCHIVED)
        logger.info(
            "Found %d archived assets. Active tab articles: %d",
            len(archived_assets),
            len(active_articles),
        )

        cleaned_count = 0
        bytes_freed = 0
        cleaned_ids = []

        for asset in archived_assets:
            # Must have verified permanent cloud backup before local temp files can be deleted
            if not asset.s3_final_url:
                continue

            # Skip if linked to an active workspace tab
            if asset.book_article and asset.book_article.strip().upper() in active_articles:
                continue

            # Candidate for deletion
            cleaned_ids.append(asset.id)
            bytes_freed += asset.file_size_bytes or 0

            if not dry_run:
                # Delete local media files
                for path in (asset.original_path, asset.preview_path, asset.ai_white_path):
                    if path:
                        try:
                            self.media_storage.delete_file(path)
                        except Exception as e:
                            logger.warning("Failed to delete temp file %s: %s", path, e)

                # Transactionally delete asset record
                with self.uow:
                    self.asset_repo.delete(asset.id)
                    self.uow.commit()

            cleaned_count += 1

        # 3. SSE event notification
        self._notify_event(
            "cleanup.finished",
            {
                "store_id": store_id,
                "cleaned_count": cleaned_count,
                "bytes_freed": bytes_freed,
                "dry_run": dry_run,
            },
        )

        return {
            "status": "success",
            "store_id": store_id,
            "cleaned_count": cleaned_count,
            "bytes_freed": bytes_freed,
            "cleaned_ids": cleaned_ids,
            "dry_run": dry_run,
        }

    def _notify_event(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.event_broker:
            try:
                self.event_broker.publish(event_type, data)
            except Exception as e:
                logger.warning("Event dispatch failed for %s: %s", event_type, e)
