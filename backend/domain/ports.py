"""Domain ports (interfaces) defining boundary contracts for external adapters.

Pure Python stdlib only (ADR-3). Uses typing.Protocol.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from backend.domain.models import Asset, Book, EnrichmentCandidate, WorkspaceTab


@runtime_checkable
class IUnitOfWork(Protocol):
    """Transactional boundary contract."""

    def __enter__(self) -> "IUnitOfWork":
        ...

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Optional[bool]:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


@runtime_checkable
class IBookRepository(Protocol):
    """Storage contract for Book entities and workspace tabs."""

    def get_by_article(self, article: str) -> Optional[Book]:
        ...

    def save(self, book: Book) -> None:
        ...

    def delete(self, article: str) -> bool:
        ...

    def search_fts(self, query: str, limit: int = 50, offset: int = 0) -> List[Book]:
        ...

    def get_next_article(self, prefix: str = "DP-B-") -> str:
        ...

    def list_tabs(self) -> List[WorkspaceTab]:
        ...

    def save_tab(self, tab: WorkspaceTab) -> None:
        ...

    def delete_tab(self, tab_id: str) -> bool:
        ...


@runtime_checkable
class IAssetRepository(Protocol):
    """Storage contract for Asset entities with Optimistic Locking."""

    def get_by_id(self, asset_id: str) -> Optional[Asset]:
        ...

    def save(self, asset: Asset) -> None:
        ...

    def list_by_article(self, article: str) -> List[Asset]:
        ...

    def delete(self, asset_id: str) -> bool:
        ...


@runtime_checkable
class IReferenceRepository(Protocol):
    """Contract for brand and dictionary autocompletion."""

    def search_brands(self, query: str, limit: int = 20) -> List[str]:
        ...

    def is_known_brand(self, brand: str) -> bool:
        ...


@runtime_checkable
class IMediaStorage(Protocol):
    """Contract for local media vault and rendered files."""

    def save_file(self, rel_path: str, data: bytes) -> str:
        ...

    def read_file(self, rel_path: str) -> bytes:
        ...

    def delete_file(self, rel_path: str) -> bool:
        ...


@runtime_checkable
class ICloudStorage(Protocol):
    """Contract for two-tier cloud storage (Yandex S3)."""

    def upload_staging(self, store_id: str, asset_id: str, render_hash: str, data: bytes) -> str:
        ...

    def promote_to_book(
        self, store_id: str, article: str, canonical_name: str, staging_key: str, sha8: str
    ) -> str:
        ...

    def get_static_card_url(self) -> str:
        ...


@runtime_checkable
class IAIVisionClient(Protocol):
    """Contract for Gemini Vision book recognizer."""

    def recognize_images(self, image_paths: List[str]) -> Dict[str, Any]:
        ...


@runtime_checkable
class IEnrichmentClient(Protocol):
    """Contract for external bibliographic metadata providers (FantLab, OpenLibrary)."""

    def search_candidates(
        self, title: str, author: str, year: Optional[int] = None, isbn: Optional[str] = None
    ) -> List[EnrichmentCandidate]:
        ...


@runtime_checkable
class IMarketplaceChannel(Protocol):
    """Contract for marketplace adapters (Ozon, Avito, etc.)."""

    def validate_book(self, book: Book) -> Dict[str, str]:
        ...

    def publish_or_update(self, book: Book) -> str:
        ...


@runtime_checkable
class IEventBroker(Protocol):
    """Contract for real-time Server-Sent Events broker."""

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        ...
