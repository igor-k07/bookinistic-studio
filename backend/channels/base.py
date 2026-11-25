"""Marketplace channel base protocol and abstractions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Protocol, runtime_checkable

from backend.domain.models import Book


@runtime_checkable
class IMarketplaceChannel(Protocol):
    """Contract for marketplace adapters (Ozon, Avito, etc.)."""

    def validate(self, book: Book) -> Dict[str, str]:
        """Validate book against marketplace rules. Returns {field: error_msg}."""
        ...

    def publish_or_update(self, book: Book) -> Dict[str, Any]:
        """Publish new item or update existing item in the marketplace."""
        ...

    def check_status(self, task_id: int) -> Dict[str, Any]:
        """Check status of asynchronous import/update task."""
        ...

    def export_file(self, books: List[Book], output_path: Path) -> Path:
        """Export catalog books to marketplace template file (e.g. Excel)."""
        ...
