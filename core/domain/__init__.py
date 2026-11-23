"""
core.domain: Пакет доменных моделей, перечислений, бизнес-правил и портов.
"""

from core.domain.enums import BookCondition, PhotoRole, TemplateMode
from core.domain.models import Book, Dimensions, PhotoItem
from core.domain.ports import (
    IAIClient,
    IBookRepository,
    ICatalogExporter,
    IImageProcessor,
    IMediaStorage,
)
from core.domain.rules import (
    SLOT_CARD,
    SLOT_COVER_BACK,
    SLOT_COVER_FRONT,
    SLOT_DEFECTS,
    SLOT_ILLUSTRATIONS,
    SLOT_INFO_PAGES,
    calculate_book_condition,
    calculate_gost_dimensions,
    classify_filename_to_slot,
    clean_publisher_name,
    format_annotation_with_warning,
    get_canonical_photo_filename,
    normalize_author_name,
    parse_format_code,
    resolve_template_mode,
)

__all__ = [
    "BookCondition",
    "PhotoRole",
    "TemplateMode",
    "Book",
    "Dimensions",
    "PhotoItem",
    "IBookRepository",
    "IMediaStorage",
    "ICatalogExporter",
    "IAIClient",
    "IImageProcessor",
    "SLOT_COVER_FRONT",
    "SLOT_COVER_BACK",
    "SLOT_INFO_PAGES",
    "SLOT_ILLUSTRATIONS",
    "SLOT_DEFECTS",
    "SLOT_CARD",
    "get_canonical_photo_filename",
    "classify_filename_to_slot",
    "calculate_book_condition",
    "calculate_gost_dimensions",
    "clean_publisher_name",
    "format_annotation_with_warning",
    "normalize_author_name",
    "parse_format_code",
    "resolve_template_mode",
]

