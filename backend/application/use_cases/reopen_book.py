"""Reopen Book Use Case.

Restores a catalog book into active workspace tabs:
- Finds book from SQLite catalog or hydrates from local Vault manifest.json.
- Checks if a workspace tab is already active to prevent duplicates.
- Persists newly opened WorkspaceTab atomically.
- Dispatches SSE event notification to UI.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.domain.exceptions import EntityNotFoundError
from backend.domain.models import Book, WorkspaceTab
from backend.domain.ports import IBookRepository, IEventBroker, IUnitOfWork, IVaultStore

logger = logging.getLogger(__name__)


class ReopenBookUseCase:
    """Use case restoring saved books from catalog or vault into desktop workspace tabs."""

    def __init__(
        self,
        uow: IUnitOfWork,
        book_repo: IBookRepository,
        vault_store: Optional[IVaultStore] = None,
        event_broker: Optional[IEventBroker] = None,
    ) -> None:
        self.uow = uow
        self.book_repo = book_repo
        self.vault_store = vault_store
        self.event_broker = event_broker

    def execute(self, article: str, tab_id: Optional[str] = None) -> WorkspaceTab:
        """Reopen a book into workspace tabs."""
        clean_art = str(article or "").strip().upper()
        if not clean_art:
            raise ValueError("Article cannot be empty")

        # 1. Retrieve book from database or local vault manifest
        book = self.book_repo.get_by_article(clean_art)
        if not book and self.vault_store:
            manifest = self.vault_store.get_manifest(clean_art)
            if manifest:
                meta = manifest.get("metadata") or manifest
                book = Book.from_dict(meta)
                # Ensure article is strictly set
                book.article = clean_art

        if not book:
            raise EntityNotFoundError(f"Book with article '{clean_art}' not found in catalog or vault archive")

        # 2. Check existing active workspace tabs to prevent duplicate tabs
        existing_tabs = self.book_repo.list_tabs()
        for tab in existing_tabs:
            if tab.book_article == clean_art:
                logger.info("Found existing active tab %s for article %s", tab.id, clean_art)
                return tab

        # 3. Create and persist new WorkspaceTab
        target_tab_id = tab_id or f"tab_{clean_art.lower()}"
        new_tab = WorkspaceTab(
            id=target_tab_id,
            book_article=clean_art,
            tab_order=len(existing_tabs),
            is_active=True,
        )

        with self.uow:
            self.book_repo.save_tab(new_tab)
            self.uow.commit()

        # 4. SSE event notification
        self._notify_event(
            "tab.opened",
            {"tab_id": new_tab.id, "article": clean_art, "title": book.title or clean_art},
        )

        return new_tab

    def _notify_event(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.event_broker:
            try:
                self.event_broker.publish(event_type, data)
            except Exception as e:
                logger.warning("Event dispatch failed for %s: %s", event_type, e)
