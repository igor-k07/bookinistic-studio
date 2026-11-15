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
    calculate_book_condition,
    calculate_gost_dimensions,
    format_annotation_with_warning,
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
    "calculate_book_condition",
    "calculate_gost_dimensions",
    "format_annotation_with_warning",
    "parse_format_code",
    "resolve_template_mode",
]

