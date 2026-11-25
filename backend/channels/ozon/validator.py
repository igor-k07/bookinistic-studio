"""Instant pre-validation of Book domain models for Ozon Seller API.

Architectural Guarantees:
- Pure synchronous execution completing in < 5 ms.
- Returns clean mapping of {field_name: error_message}.
- Empty dict {} indicates 100% readiness for Ozon publication.
- Enforces ADR-4 era boundary (year <= 2010 vs year >= 2011 ISBN requirement).
- Zero external network dependencies.
"""

from __future__ import annotations

from typing import Dict

from backend.domain.enums import BookEra
from backend.domain.models import Book
from backend.domain.rules import resolve_book_era
from backend.domain.value_objects import Isbn


class OzonValidator:
    """Pre-validation engine enforcing Ozon marketplace requirements."""

    @staticmethod
    def validate(book: Book) -> Dict[str, str]:
        """Validate book entity against Ozon rules, returning field -> error dict."""
        errors: Dict[str, str] = {}

        # 1. Title is required and non-empty
        if not book.title or not book.title.strip():
            errors["title"] = "Название книги обязательно для публикации на Ozon"

        # 2. Price is required and positive
        if not book.price or book.price <= 0:
            errors["price"] = "Цена книги должна быть указана и превышать 0 руб."

        # 3. Year and Era boundary (ADR-4)
        if not book.year or book.year <= 0:
            errors["year"] = "Год издания обязателен для заполнения"
        else:
            era = resolve_book_era(book.year)
            if era == BookEra.POST2011:
                # For books >= 2011, ISBN is mandatory on Ozon
                if not book.isbn:
                    errors["isbn"] = (
                        f"Для современных книг (год {book.year} >= 2011) "
                        "наличие валидного ISBN обязательно на Ozon"
                    )
                else:
                    parsed_isbn = Isbn.parse(book.isbn)
                    if not parsed_isbn or not parsed_isbn.is_valid:
                        errors["isbn"] = f"Указан невалидный номер ISBN: '{book.isbn}'"

        # 4. Brand or Publisher
        brand_val = (book.brand or "").strip()
        pub_val = (book.publisher or "").strip()
        if not brand_val and not pub_val:
            errors["publisher"] = (
                "Необходимо указать наименование издательства или бренд для Ozon"
            )

        # 5. Dimensions and weight (required for Ozon logistics calculation)
        if not book.dimensions or book.dimensions.weight_g <= 0:
            errors["weight_g"] = "Вес книги обязателен и должен быть больше 0 грамм"
        if not book.dimensions or book.dimensions.width_mm <= 0:
            errors["width_mm"] = "Ширина книги должна быть больше 0 мм"
        if not book.dimensions or book.dimensions.length_mm <= 0:
            errors["length_mm"] = "Длина (высота) книги должна быть больше 0 мм"
        if not book.dimensions or book.dimensions.height_mm <= 0:
            errors["height_mm"] = "Толщина (корешок) книги должна быть больше 0 мм"

        # 6. Primary photo requirement
        if not book.main_photo_url:
            has_cover = any(
                str(getattr(p, "role", "")).lower() in ("cover_front", "обложка")
                for p in book.photos
            )
            if not has_cover:
                errors["photos"] = (
                    "Для публикации на Ozon требуется хотя бы одна фотография обложки (main_photo)"
                )

        return errors
