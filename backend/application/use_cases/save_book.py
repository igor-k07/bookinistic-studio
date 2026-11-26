"""Save Book Use Case.

Single entrypoint for '💾 Сохранить':
- Applies v1 domain rules (EAN-13 auto-gen, defect warning mantra, era boundary).
- Instant Ozon pre-validation (< 5ms, skippable for drafts/partial saves).
- VaultStore archive persistence (manifest.json + local render/original isolation).
- S3 CopyObject photo promotion to permanent CDN URLs.
- Atomic SQLite persistence (Book entity + Asset ARCHIVED + WorkspaceTab cleanup + Outbox enqueue).
- OpenXmlDomExporter row update/insert without regex.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.domain.enums import AssetStatus, OzonSyncStatus
from backend.domain.exceptions import ValidationError
from backend.domain.models import Book
from backend.domain.ports import (
    IAssetRepository,
    IBookRepository,
    ICloudStorage,
    IEventBroker,
    IExcelExporter,
    IMarketplaceChannel,
    IUnitOfWork,
    IVaultStore,
)
from backend.domain.rules import (
    calculate_book_condition,
    format_annotation_with_warning,
    resolve_book_era,
)
from backend.domain.value_objects import Ean13

logger = logging.getLogger(__name__)


class SaveBookUseCase:
    """Use case managing atomic persistence and marketplace submission for books."""

    def __init__(
        self,
        uow: IUnitOfWork,
        book_repo: IBookRepository,
        channel: IMarketplaceChannel,
        vault_store: Optional[IVaultStore] = None,
        cloud_storage: Optional[ICloudStorage] = None,
        excel_exporter: Optional[IExcelExporter] = None,
        event_broker: Optional[IEventBroker] = None,
        asset_repo: Optional[IAssetRepository] = None,
        outbox_worker: Optional[Any] = None,
    ) -> None:
        self.uow = uow
        self.book_repo = book_repo
        self.channel = channel
        self.vault_store = vault_store
        self.cloud_storage = cloud_storage
        self.excel_exporter = excel_exporter
        self.event_broker = event_broker
        self.asset_repo = asset_repo
        self.outbox_worker = outbox_worker

    def execute(
        self,
        store_id: str,
        book: Book,
        photos: Optional[List[Tuple[str, bytes, Optional[bytes]]]] = None,
        staging_keys: Optional[Dict[str, str]] = None,
        skip_validation: bool = False,
    ) -> Dict[str, Any]:
        """Atomically validate, archive, export, and persist a book."""
        # 0. Gather assigned assets & apply v1 domain rules
        assigned_assets = self.asset_repo.list_by_article(book.article) if self.asset_repo else []
        has_defects = any(
            (a.slot or "") in ("mantra_defects", "defects", "defect") for a in assigned_assets
        )
        if not book.barcode and book.article:
            try:
                book.barcode = str(Ean13.from_article(book.article))
            except Exception:
                pass
        book.template_mode = resolve_book_era(book.year)
        book.condition = calculate_book_condition(has_defects, book.condition)
        book.annotation = format_annotation_with_warning(
            book.annotation, has_defects, book.condition.value
        )

        # 1. Instant Ozon Pre-Validation
        if not skip_validation:
            validation_errors = self.channel.validate(book)
            if validation_errors:
                logger.warning("Validation failed for %s: %s", book.article, validation_errors)
                raise ValidationError(f"Ozon pre-validation failed: {validation_errors}")

        # 2. Build vault photos from assigned assets if caller didn't pass raw bytes
        vault_photos = photos
        if vault_photos is None and assigned_assets:
            built: List[Tuple[str, bytes, Optional[bytes]]] = []
            for idx, a in enumerate(assigned_assets):
                src = Path(a.preview_path or a.original_path)
                if src.is_file():
                    orig = Path(a.original_path)
                    orig_bytes = orig.read_bytes() if orig.is_file() else None
                    slot_name = a.slot or "other"
                    fname = f"{idx + 1:02d}_{slot_name}.jpg"
                    built.append((fname, src.read_bytes(), orig_bytes))
            if built:
                vault_photos = built

        if self.vault_store and vault_photos:
            try:
                self.vault_store.save_book_vault(
                    article=book.article,
                    book_metadata=book.to_dict(),
                    photos=vault_photos,
                )
            except Exception as e:
                logger.error("VaultStore archiving error for %s: %s", book.article, e)
                raise

        # 3. S3 Staging -> Production Promotion (Server-side CopyObject ~30ms)
        if self.cloud_storage and staging_keys:
            promoted_urls: List[str] = []
            for canonical_name, staging_key in staging_keys.items():
                try:
                    url = self.cloud_storage.promote_to_book(
                        store_id=store_id,
                        article=book.article,
                        canonical_name=canonical_name,
                        staging_key=staging_key,
                        sha8=staging_key[-8:] if len(staging_key) >= 8 else "00000000",
                    )
                    promoted_urls.append(url)
                except Exception as e:
                    logger.warning("Failed to promote photo %s: %s", canonical_name, e)

            if promoted_urls:
                book.main_photo_url = promoted_urls[0]
                book.add_photo_urls = promoted_urls[1:14]
                static_card = self.cloud_storage.get_static_card_url()
                if static_card and static_card not in book.add_photo_urls and len(book.add_photo_urls) < 13:
                    book.add_photo_urls.append(static_card)

        # 4. Atomic SQLite Unit of Work: Book + Asset ARCHIVED + Tab Cleanup
        with self.uow:
            book.status = "SAVED"
            book.ozon_sync_status = OzonSyncStatus.QUEUED
            self.book_repo.save(book)

            if self.asset_repo and assigned_assets:
                for a in assigned_assets:
                    a.status = AssetStatus.ARCHIVED
                    self.asset_repo.save(a)

            for tab in self.book_repo.list_tabs():
                if tab.book_article == book.article:
                    self.book_repo.delete_tab(tab.id)

            self.uow.commit()

        # 5. Enqueue into Ozon Outbox Worker
        if self.outbox_worker is not None:
            try:
                self.outbox_worker.enqueue(book.article, store_id)
            except Exception as e:
                logger.warning("Failed to enqueue %s to Ozon outbox: %s", book.article, e)

        # 6. OpenXML DOM Excel Export (after SQLite commit so repo has latest book)
        excel_path: Optional[str] = None
        if self.excel_exporter:
            try:
                excel_path = self.excel_exporter.export_book(book)
            except Exception as e:
                logger.error("Excel export error for %s: %s", book.article, e)
                raise

        # 7. Event Dispatch
        self._notify_event(
            "book.saved",
            {"article": book.article, "store_id": store_id, "status": "SAVED"},
        )

        return {
            "success": True,
            "status": "success",
            "article": book.article,
            "excel_path": excel_path,
            "book": book.to_dict(),
        }

    def _notify_event(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.event_broker:
            try:
                self.event_broker.publish(event_type, data)
            except Exception as e:
                logger.warning("Event dispatch failed for %s: %s", event_type, e)
