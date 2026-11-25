"""Domain layer for Bookinistic Studio 2.0 (ADR-3: pure stdlib, zero dependencies)."""

from backend.domain.enums import (
    AssetStatus,
    BookCondition,
    BookEra,
    FieldSource,
    OzonSyncStatus,
    PhotoRole,
    TemplateMode,
)
from backend.domain.exceptions import (
    ArticleConflictError,
    ConcurrencyError,
    DomainError,
    ResourceNotFoundError,
    ValidationError,
)
from backend.domain.value_objects import (
    Article,
    Dimensions,
    Ean13,
    Isbn,
    Price,
)

__all__ = [
    "Article",
    "ArticleConflictError",
    "AssetStatus",
    "BookCondition",
    "BookEra",
    "ConcurrencyError",
    "Dimensions",
    "DomainError",
    "Ean13",
    "FieldSource",
    "Isbn",
    "OzonSyncStatus",
    "PhotoRole",
    "Price",
    "ResourceNotFoundError",
    "TemplateMode",
    "ValidationError",
]
