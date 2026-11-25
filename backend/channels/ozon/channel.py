"""Ozon marketplace channel adapter implementing IMarketplaceChannel."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from backend.channels.base import IMarketplaceChannel
from backend.channels.ozon.gateway import OzonGateway
from backend.channels.ozon.mapper import (
    book_to_ozon_attributes_payload,
    book_to_ozon_import_payload,
)
from backend.channels.ozon.validator import OzonValidator
from backend.domain.models import Book

logger = logging.getLogger(__name__)


class OzonChannel(IMarketplaceChannel):
    """High-level Ozon Seller Channel conforming to IMarketplaceChannel."""

    def __init__(self, gateway: OzonGateway) -> None:
        self.gateway = gateway
        self.validator = OzonValidator()

    def validate(self, book: Book) -> Dict[str, str]:
        """Instant pre-validation returning {field: error_msg}."""
        return self.validator.validate(book)

    def publish_or_update(self, book: Book) -> Dict[str, Any]:
        """Validate and either update existing product or import as new."""
        errors = self.validate(book)
        if errors:
            return {"success": False, "errors": errors}

        # Check existence by offer_id
        existing = self.gateway.get_products_info(offer_ids=[book.article])
        if existing:
            logger.info("Product %s exists in Ozon; updating attributes", book.article)
            payload = book_to_ozon_attributes_payload(book)
            res = self.gateway.update_attributes(payload)

            if book.price and book.price > 0:
                price_str = str(int(book.price))
                old_str = str(int(book.old_price)) if book.old_price else ""

                self.gateway.update_prices({
                    "prices": [
                        {
                            "offer_id": book.article,
                            "price": price_str,
                            "old_price": old_str,
                        }
                    ]
                })

            return {"success": True, "action": "update", "result": res}
        else:
            logger.info("Product %s does not exist in Ozon; importing new item", book.article)
            payload = book_to_ozon_import_payload(book)
            res = self.gateway.import_products(payload)
            return {"success": True, "action": "import", "result": res}

    def check_status(self, task_id: int) -> Dict[str, Any]:
        """Check status of asynchronous import task."""
        return self.gateway.get_import_info(task_id)

    def export_file(self, books: List[Book], output_path: Path) -> Path:
        """Export catalog books to Ozon template Excel file (implemented in Step 4.3)."""
        raise NotImplementedError("OpenXmlDomExporter handles Excel file exports")
