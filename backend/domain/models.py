"""Domain entity models for Bookinistic Studio 2.0.

Pure Python stdlib only (ADR-3). Zero external dependencies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from backend.domain.enums import (
    AssetStatus,
    BookCondition,
    BookEra,
    FieldSource,
    OzonSyncStatus,
)
from backend.domain.value_objects import Dimensions


@dataclass
class Book:
    """Core domain model representing a cataloged book edition."""

    article: str
    title: str = ""
    author: str = "не указан"
    year: Optional[int] = None
    price: float = 0.0
    template_mode: BookEra = BookEra.PRE2011
    status: str = "DRAFT"
    storage_location: str = ""  # Shelf / Box / Bin for 58x40 thermal labels
    publisher: str = ""
    series: str = ""
    isbn: str = ""
    format_code: str = ""
    pages: int = 0
    cover_type: str = "Твердый переплет"
    condition: BookCondition = BookCondition.GOOD
    annotation: str = ""
    brand: str = ""
    author_cover: str = ""
    original_title: str = ""
    barcode: str = ""
    genre: str = "Проза"
    paper_type: str = ""
    age_limit: str = ""
    translator: str = ""
    illustrator: str = ""
    old_price: Optional[float] = None
    main_photo_url: str = ""
    add_photo_urls: List[str] = field(default_factory=list)
    dimensions: Dimensions = field(default_factory=Dimensions)
    field_sources: Dict[str, FieldSource] = field(default_factory=dict)
    suggestions: Dict[str, Any] = field(default_factory=dict)
    photos: List[str] = field(default_factory=list)
    ozon_sync_status: Optional[OzonSyncStatus] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


    def to_dict(self) -> Dict[str, Any]:
        """Convert Book model to JSON-serializable dictionary."""
        d = asdict(self)
        d["template_mode"] = self.template_mode.value
        d["condition"] = self.condition.value
        d["field_sources"] = {k: v.value if isinstance(v, FieldSource) else int(v) for k, v in self.field_sources.items()}
        d["dimensions"] = self.dimensions.to_dict()
        if self.ozon_sync_status:
            d["ozon_sync_status"] = (
                self.ozon_sync_status.value
                if isinstance(self.ozon_sync_status, OzonSyncStatus)
                else str(self.ozon_sync_status)
            )
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Book":
        """Instantiate Book model safely from a dictionary."""
        if not isinstance(data, dict):
            raise TypeError("Book.from_dict requires a dictionary")

        era = BookEra(data.get("template_mode", BookEra.PRE2011.value))
        cond = BookCondition.from_str(data.get("condition"))
        dims = Dimensions.from_dict(data.get("dimensions"))

        raw_sources = data.get("field_sources") or {}
        sources: Dict[str, FieldSource] = {}
        if isinstance(raw_sources, dict):
            for k, v in raw_sources.items():
                try:
                    sources[k] = FieldSource(int(v))
                except (ValueError, TypeError):
                    sources[k] = FieldSource.DEFAULT

        raw_year = data.get("year")
        year_val: Optional[int] = None
        if raw_year is not None and str(raw_year).strip():
            try:
                year_val = int(raw_year)
            except (ValueError, TypeError):
                year_val = None

        raw_price = data.get("price")
        price_val: float = 0.0
        if raw_price is not None:
            try:
                price_val = float(raw_price)
            except (ValueError, TypeError):
                price_val = 0.0

        sync_val = data.get("ozon_sync_status")
        try:
            sync_status = OzonSyncStatus(sync_val) if sync_val else None
        except ValueError:
            sync_status = None

        raw_add = data.get("add_photo_urls")
        if raw_add is None:
            raw_add = data.get("images")
        if isinstance(raw_add, str):
            import re as _re

            parsed_add = [u.strip() for u in _re.split(r"[\s;]+", raw_add) if u.strip().startswith("http")]
        elif isinstance(raw_add, (list, tuple)):
            parsed_add = [str(u).strip() for u in raw_add if str(u).strip()]
        else:
            parsed_add = []

        main_url = str(data.get("main_photo_url") or data.get("primary_image") or "").strip()

        return cls(
            article=str(data.get("article", "")).strip().upper(),
            title=str(data.get("title", "")).strip(),
            author=str(data.get("author", "не указан")).strip() or "не указан",
            year=year_val,
            price=price_val,
            template_mode=era,
            status=str(data.get("status", "DRAFT")),
            storage_location=str(data.get("storage_location", "")).strip(),
            publisher=str(data.get("publisher", "")).strip(),
            series=str(data.get("series", "")).strip(),
            isbn=str(data.get("isbn", "")).strip(),
            format_code=str(data.get("format_code", "")).strip(),
            pages=int(data.get("pages") or 0),
            cover_type=str(data.get("cover_type", "Твердый переплет")),
            condition=cond,
            annotation=str(data.get("annotation", "")).strip(),
            brand=str(data.get("brand", "")).strip(),
            author_cover=str(data.get("author_cover", "")).strip(),
            original_title=str(data.get("original_title", "")).strip(),
            barcode=str(data.get("barcode", "")).strip(),
            genre=str(data.get("genre", "Проза")).strip() or "Проза",
            paper_type=str(data.get("paper_type", "")).strip(),
            age_limit=str(data.get("age_limit", "")).strip(),
            translator=str(data.get("translator", "")).strip(),
            illustrator=str(data.get("illustrator", "")).strip(),
            old_price=float(data["old_price"]) if data.get("old_price") not in (None, "") else None,
            main_photo_url=main_url,
            add_photo_urls=parsed_add,
            dimensions=dims,
            field_sources=sources,
            suggestions=data.get("suggestions") or {},
            photos=list(data.get("photos") or []),
            ozon_sync_status=sync_status,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )



@dataclass
class Asset:
    """Unified Photo Registry Asset model (Photo Engine V3)."""

    id: str
    book_article: Optional[str] = None
    slot: Optional[str] = None
    slot_order: int = 0
    status: AssetStatus = AssetStatus.UPLOADED
    status_message: str = ""
    original_path: str = ""
    preview_path: str = ""
    ai_white_path: Optional[str] = None
    transformations: Dict[str, Any] = field(default_factory=dict)
    render_hash: str = ""
    s3_staging_url: Optional[str] = None
    s3_final_url: Optional[str] = None
    s3_uploaded_hash: Optional[str] = None
    version: int = 1
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert Asset model to JSON-serializable dictionary."""
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Asset":
        """Instantiate Asset from dictionary."""
        status_val = data.get("status", AssetStatus.UPLOADED.value)
        try:
            status = AssetStatus(status_val)
        except ValueError:
            status = AssetStatus.UPLOADED

        return cls(
            id=str(data.get("id", "")),
            book_article=data.get("book_article"),
            slot=data.get("slot"),
            slot_order=int(data.get("slot_order") or 0),
            status=status,
            status_message=str(data.get("status_message", "")),
            original_path=str(data.get("original_path", "")),
            preview_path=str(data.get("preview_path", "")),
            ai_white_path=data.get("ai_white_path"),
            transformations=dict(data.get("transformations") or {}),
            render_hash=str(data.get("render_hash", "")),
            s3_staging_url=data.get("s3_staging_url"),
            s3_final_url=data.get("s3_final_url"),
            s3_uploaded_hash=data.get("s3_uploaded_hash"),
            version=int(data.get("version") or 1),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            file_size_bytes=int(data.get("file_size_bytes") or 0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class WorkspaceTab:
    """Active desktop workspace tab model."""

    id: str = ""
    book_article: str = ""
    tab_order: int = 0
    is_active: bool = False
    is_edit_mode: bool = False
    title: str = ""
    book_data: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None

    def __init__(
        self,
        id: str = "",
        book_article: str = "",
        tab_order: int = 0,
        is_active: bool = False,
        is_edit_mode: bool = False,
        title: str = "",
        book_data: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
        tab_id: Optional[str] = None,
        article: Optional[str] = None,
    ) -> None:
        self.id = tab_id or id or ""
        self.book_article = article or book_article or ""
        self.tab_order = tab_order
        self.is_active = is_active
        self.is_edit_mode = is_edit_mode
        self.title = title
        self.book_data = book_data or {}
        self.created_at = created_at

    @property
    def tab_id(self) -> str:
        return self.id

    @tab_id.setter
    def tab_id(self, val: str) -> None:
        self.id = val

    @property
    def article(self) -> str:
        return self.book_article

    @article.setter
    def article(self, val: str) -> None:
        self.book_article = val


@dataclass
class OutboxItem:
    """Marketplace transactional outbox queue item."""

    id: Optional[int] = None
    channel: str = "ozon"
    book_article: str = ""
    action: str = "publish_or_update"
    status: OzonSyncStatus = OzonSyncStatus.QUEUED
    external_task_id: Optional[str] = None
    attempts: int = 0
    next_retry_at: Optional[str] = None
    last_error: str = ""
    error_fields: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class EnrichmentCandidate:
    """Candidate match returned by external bibliographic provider."""

    provider: str = ""
    exact_match: bool = False
    fields: Dict[str, Any] = field(default_factory=dict)
    match_type: str = "exact"

    def __init__(
        self,
        provider: str = "",
        exact_match: bool = False,
        fields: Optional[Dict[str, Any]] = None,
        match_type: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.fields = fields or {}
        self.match_type = match_type or ("exact" if exact_match else "fuzzy")
        self.exact_match = exact_match or (self.match_type == "exact")
