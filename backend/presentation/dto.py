"""Pydantic v2 Data Transfer Objects (DTOs) for API contracts and OpenAPI schema generation.

Strict type validation for all inbound and outbound HTTP requests.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DimensionsDTO(BaseModel):
    width_mm: int = Field(default=130, ge=0)
    length_mm: int = Field(default=200, ge=0)
    height_mm: int = Field(default=15, ge=0)
    weight_g: int = Field(default=250, ge=0)
    book_format_code: str = Field(default="")


class BookDTO(BaseModel):
    article: str = Field(default="")
    title: str = Field(default="")
    author: str = Field(default="не указан")
    year: Optional[int] = Field(default=None)
    price: float = Field(default=0.0, ge=0.0)
    old_price: Optional[float] = Field(default=None, ge=0.0)
    template_mode: str = Field(default="pre2011")
    status: str = Field(default="DRAFT")
    storage_location: str = Field(default="")
    publisher: str = Field(default="")
    series: str = Field(default="")
    isbn: str = Field(default="")
    format_code: str = Field(default="")
    pages: int = Field(default=0, ge=0)
    cover_type: str = Field(default="Твердый переплет")
    condition: str = Field(default="Хорошая")
    annotation: str = Field(default="")
    brand: str = Field(default="")
    author_cover: str = Field(default="")
    original_title: str = Field(default="")
    barcode: str = Field(default="")
    genre: str = Field(default="Проза")
    paper_type: str = Field(default="")
    age_limit: str = Field(default="")
    translator: str = Field(default="")
    illustrator: str = Field(default="")
    main_photo_url: str = Field(default="")
    add_photo_urls: List[str] = Field(default_factory=list)
    dimensions: DimensionsDTO = Field(default_factory=DimensionsDTO)
    field_sources: Dict[str, int] = Field(default_factory=dict)
    suggestions: Dict[str, Any] = Field(default_factory=dict)
    ozon_sync_status: Optional[str] = Field(default=None)


class WorkspaceTabDTO(BaseModel):
    id: str
    book_article: str
    tab_order: int = Field(default=0)
    is_active: bool = Field(default=False)
    is_edit_mode: bool = Field(default=False)
    title: str = Field(default="")
    created_at: Optional[str] = Field(default=None)


class AssetDTO(BaseModel):
    id: str
    book_article: Optional[str] = Field(default=None)
    slot: Optional[str] = Field(default=None)
    slot_order: int = Field(default=0)
    status: str = Field(default="UPLOADED")
    status_message: str = Field(default="")
    original_path: str = Field(default="")
    preview_path: str = Field(default="")
    ai_white_path: Optional[str] = Field(default=None)
    transformations: Dict[str, Any] = Field(default_factory=dict)
    render_hash: str = Field(default="")
    s3_staging_url: Optional[str] = Field(default=None)
    s3_final_url: Optional[str] = Field(default=None)
    version: int = Field(default=1)
    file_size_bytes: int = Field(default=0)


class SaveBookRequest(BaseModel):
    book: BookDTO
    store_id: str = Field(default="default")
    skip_validation: bool = Field(default=False)


class ValidateBookRequest(BaseModel):
    book: BookDTO


class ReopenBookRequest(BaseModel):
    article: str
    tab_id: Optional[str] = Field(default=None)


class TransformAssetRequest(BaseModel):
    transformations: Dict[str, Any] = Field(default_factory=dict)
    expected_version: int = Field(ge=1)


class AssignAssetSlotRequest(BaseModel):
    slot: str
    slot_order: int = Field(default=0)


class RecognizeRequest(BaseModel):
    book: BookDTO
    photos: List[List[str]] = Field(default_factory=list)  # [[path, role], ...]


class ApplySuggestionRequest(BaseModel):
    book_article: str
    field_name: str
    value: Any


class ClassifyBatchRequest(BaseModel):
    filenames: List[str]


class MobileCommitDTO(BaseModel):
    session_id: str
    store_id: str = Field(default="default")
    book_article: Optional[str] = Field(default=None)
    photo_roles: List[Dict[str, str]] = Field(default_factory=list)


class SwitchProfileRequest(BaseModel):
    store_id: str


class SyncSmartS3Request(BaseModel):
    store_id: str = Field(default="default")
    batch_size: int = Field(default=50, le=50)


class BootstrapResponse(BaseModel):
    stores: List[Dict[str, Any]]
    active_store: str
    brands: List[str]
    gost_formats: Dict[str, Any]
    tabs: List[WorkspaceTabDTO]
    mobile_token: str
    tunnel_url: Optional[str] = None


class CatalogSearchResponse(BaseModel):
    books: List[BookDTO]
    total: int
    query: str
