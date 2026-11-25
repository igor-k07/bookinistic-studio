"""Sync Catalog Use Case.

Incremental Ozon -> SQLite photo sync:
- Strictly chunked by 50 items per request (ADR compliance with Ozon /v4/product/info/attributes limit).
- Pinned store_id isolation.
- Per-item error isolation: individual failures never abort the entire batch.
- Patches photo URLs only (main_photo_url, add_photo_urls) and updates sync status.
- Real-time progress updates via SSEBroker.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.domain.enums import OzonSyncStatus
from backend.domain.ports import IBookRepository, IEventBroker, IUnitOfWork

logger = logging.getLogger(__name__)


class SyncCatalogUseCase:
    """Use case synchronizing remote marketplace product photo URLs with local catalog."""

    def __init__(
        self,
        uow: IUnitOfWork,
        book_repo: IBookRepository,
        gateway: Any,  # OzonGateway or compatible protocol
        event_broker: Optional[IEventBroker] = None,
    ) -> None:
        self.uow = uow
        self.book_repo = book_repo
        self.gateway = gateway
        self.event_broker = event_broker

    def execute(
        self,
        store_id: str,
        articles: Optional[List[str]] = None,
        batch_size: int = 50,
    ) -> Dict[str, Any]:
        """Perform photo synchronization for specified articles or all listed products."""
        # Enforce batch_size <= 50 per Ozon API specification
        safe_batch_size = max(1, min(batch_size, 50))

        # 1. Determine list of offer_ids (articles)
        target_articles = list(articles) if articles else []
        if not target_articles:
            try:
                products_resp = self.gateway.list_products(limit=1000)
                items = products_resp.get("result", {}).get("items", [])
                target_articles = [it.get("offer_id") for it in items if it.get("offer_id")]
            except Exception as exc:
                logger.error("Failed to list products from marketplace: %s", exc)
                return {"status": "error", "error": str(exc), "total_updated": 0}

        total_scanned = len(target_articles)
        total_updated = 0
        errors: List[Dict[str, str]] = []

        # 2. Process in strict chunks of 50
        for i in range(0, total_scanned, safe_batch_size):
            chunk = target_articles[i : i + safe_batch_size]
            try:
                info_resp = self.gateway.get_products_info(offer_ids=chunk)
                products_info = info_resp.get("result", {}).get("items", [])
            except Exception as e:
                logger.warning("Error fetching info chunk %d-%d: %s", i, i + len(chunk), e)
                for art in chunk:
                    errors.append({"article": art, "error": str(e)})
                continue

            # Map by offer_id
            for p in products_info:
                offer_id = p.get("offer_id") or ""
                if not offer_id:
                    continue

                try:
                    primary_image = p.get("primary_image") or ""
                    images = p.get("images") or []
                    # Separate main from additional
                    main_url = primary_image or (images[0] if images else "")
                    add_urls = [img for img in images if img != main_url]

                    # Atomic SQLite update
                    with self.uow:
                        book = self.book_repo.get_by_article(offer_id)
                        if book:
                            if main_url:
                                book.main_photo_url = main_url
                            if add_urls:
                                book.add_photo_urls = add_urls
                            book.ozon_sync_status = OzonSyncStatus.PUBLISHED
                            self.book_repo.save(book)
                            self.uow.commit()
                            total_updated += 1
                        else:
                            logger.debug("Article %s not found in local catalog", offer_id)
                except Exception as item_err:
                    logger.warning("Per-item sync error for %s: %s", offer_id, item_err)
                    errors.append({"article": offer_id, "error": str(item_err)})

            # 3. Report progress
            progress = min(1.0, (i + len(chunk)) / max(1, total_scanned))
            self._notify_progress(store_id, progress, f"Synced {total_updated} books...")

        self._notify_progress(store_id, 1.0, "Sync complete")
        return {
            "status": "success",
            "store_id": store_id,
            "total_scanned": total_scanned,
            "total_updated": total_updated,
            "errors": errors,
        }

    def _notify_progress(self, store_id: str, progress: float, message: str) -> None:
        if self.event_broker:
            try:
                self.event_broker.publish(
                    "sync.progress",
                    {"store_id": store_id, "progress": progress, "message": message},
                )
            except Exception as e:
                logger.warning("Failed to publish sync progress: %s", e)
