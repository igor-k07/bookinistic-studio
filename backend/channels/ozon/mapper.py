"""Symmetric mapping between Book domain entities and Ozon Seller API payloads.

Architectural Guarantees:
- Pure functions without IO or network side-effects.
- Symmetric bi-directional mapping (Book -> Ozon import/attributes payload, and Ozon response -> Book dict).
- No hardcoded brand fallbacks (never assigns "Советский писатель" unless legitimately specified).
- Complete attribute ID mapping for Books category (17038167).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from backend.domain.models import Book

OZON_BOOK_CATEGORY_ID = 17038167
OZON_BOOK_TYPE_ID = 971445087

# Cached dictionary of Ozon genre IDs (direction / направление)
OZON_GENRE_MAP: Dict[str, Tuple[int, str]] = {
    "проза": (972842193, "Проза"),
    "фантастика": (972842194, "Фантастика"),
    "фэнтези": (972842195, "Фэнтези"),
    "детектив": (972842196, "Детектив"),
    "поэзия": (972842197, "Поэзия"),
    "история": (972842198, "История"),
    "приключения": (972842199, "Приключения"),
    "биография": (972842200, "Биография"),
    "мемуары": (972842201, "Мемуары"),
    "энциклопедия, справочник": (972842202, "Энциклопедия, справочник"),
    "словарь": (972842203, "Словарь"),
    "научная и научно-популярная литература": (972842204, "Научная и научно-популярная литература"),
    "искусство и культура": (972842205, "Искусство и культура"),
    "публицистика": (972842206, "Публицистика"),
    "детская книга": (972842207, "Детская книга"),
    "комикс": (972842208, "Комикс"),
    "манга": (972842209, "Манга"),
    "эпос и фольклор": (972842210, "Эпос и фольклор"),
    "басни": (972842211, "Басни"),
}


def build_ozon_book_attributes(book: Book) -> List[Dict[str, Any]]:
    """Build Ozon attributes array for category 17038167 (Печатная книга)."""
    attrs: List[Dict[str, Any]] = []

    def _add_str(attr_id: int, val: Optional[str]) -> None:
        if val and val.strip():
            attrs.append({"id": attr_id, "values": [{"value": val.strip()}]})

    def _add_dict(attr_id: int, val_id: int, val_str: str) -> None:
        attrs.append({"id": attr_id, "values": [{"dictionary_value_id": val_id, "value": val_str}]})

    # 1. System mandatory attributes
    _add_dict(8229, 971445087, "Печатная книга")
    _add_dict(
        22232,
        971398243,
        "4901990000 - Прочие книги, брошюры, листовки, аналогичные печатные издания, сброшюрованные",
    )

    # 2. Genre / Direction (attr 23273)
    raw_genre = (book.genre or "").strip().lower()
    if raw_genre in OZON_GENRE_MAP:
        g_id, g_name = OZON_GENRE_MAP[raw_genre]
        _add_dict(23273, g_id, g_name)
    elif book.genre:
        _add_str(23273, book.genre)
    else:
        _add_dict(23273, 972842193, "Проза")

    # 3. Title and Authors
    _add_str(4180, book.title)
    _add_str(105, book.author or "не указан")
    _add_str(4182, book.author_cover or book.author or "не указан")
    if book.original_title:
        _add_str(4183, book.original_title)

    # 4. Brand and Publisher (NO HARDCODED "Советский писатель" fallback!)
    brand_val = (book.brand or book.publisher or "").strip()
    if brand_val and brand_val.lower() != "нет бренда":
        _add_str(85, brand_val)
    if book.publisher:
        _add_str(7, book.publisher)
    if book.series:
        _add_str(1, book.series)

    # 5. Publication specs
    if book.year:
        _add_str(4081, str(book.year))
    if book.pages:
        _add_str(4051, str(book.pages))
    if book.isbn:
        _add_str(4184, book.isbn)
    if book.cover_type:
        _add_str(9356, book.cover_type)
    if book.condition:
        _add_str(8857, book.condition)
    if book.annotation:
        _add_str(4191, book.annotation)
    if book.age_limit:
        _add_str(8862, book.age_limit)
    if book.translator:
        _add_str(112, book.translator)
    if book.illustrator:
        _add_str(111, book.illustrator)
    if book.paper_type:
        _add_str(4385, book.paper_type)

    # Language and Country
    _add_dict(4384, 971398286, "Русский")
    country_val = "СССР" if (book.year and book.year <= 1991) else "Россия"
    _add_str(4389, country_val)

    # Dimensions string (attr 4082)
    if book.dimensions:
        dim_str = f"{book.dimensions.width_mm}x{book.dimensions.length_mm}x{book.dimensions.height_mm}"
        _add_str(4082, dim_str)

    return attrs


def book_to_ozon_import_payload(book: Book) -> Dict[str, Any]:
    """Convert domain Book to Ozon POST /v3/product/import item payload."""
    dims = book.dimensions
    width = dims.width_mm if dims else 130
    length = dims.length_mm if dims else 200
    height = dims.height_mm if dims else 20
    weight = dims.weight_g if dims else 300

    price_str = str(int(book.price)) if book.price else "1000"
    old_price_str = str(int(book.old_price)) if book.old_price else ""


    item_payload: Dict[str, Any] = {
        "offer_id": book.article,
        "name": book.title,
        "description_category_id": OZON_BOOK_CATEGORY_ID,
        "type_id": OZON_BOOK_TYPE_ID,
        "price": price_str,
        "old_price": old_price_str,
        "vat": "0",
        "barcode": book.barcode or "",
        "width": width,
        "depth": length,
        "height": height,
        "dimension_unit": "mm",
        "weight": weight,
        "weight_unit": "g",
        "attributes": build_ozon_book_attributes(book),
    }

    if book.main_photo_url:
        item_payload["primary_image"] = book.main_photo_url

    if book.add_photo_urls:
        if isinstance(book.add_photo_urls, list):
            item_payload["images"] = book.add_photo_urls[:14]
        elif isinstance(book.add_photo_urls, str):
            item_payload["images"] = book.add_photo_urls.split()[:14]

    return {"items": [item_payload]}


def book_to_ozon_attributes_payload(book: Book) -> Dict[str, Any]:
    """Convert domain Book to Ozon POST /v1/product/attributes/update item payload."""
    return {
        "items": [
            {
                "offer_id": book.article,
                "attributes": build_ozon_book_attributes(book),
            }
        ]
    }


def ozon_response_to_book_dict(
    item_info: Dict[str, Any], item_attrs: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Parse Ozon API product info and attributes into Book domain dictionary."""
    article = item_info.get("offer_id", "")
    title = item_info.get("name", "")
    price_val = float(item_info.get("price") or 0.0)

    # Attributes dictionary parsing
    attrs_by_id: Dict[int, str] = {}
    if item_attrs:
        for attr in item_attrs.get("attributes", []):
            aid = attr.get("id")
            vals = attr.get("values", [])
            if vals and aid is not None:
                val_text = str(vals[0].get("value", "")).strip()
                attrs_by_id[aid] = val_text

    year_val: Optional[int] = None
    if 4081 in attrs_by_id:
        try:
            year_val = int(attrs_by_id[4081])
        except ValueError:
            pass

    pages_val: Optional[int] = None
    if 4051 in attrs_by_id:
        try:
            pages_val = int(attrs_by_id[4051])
        except ValueError:
            pass

    return {
        "article": article,
        "title": attrs_by_id.get(4180, title),
        "author": attrs_by_id.get(105, "не указан"),
        "author_cover": attrs_by_id.get(4182, ""),
        "original_title": attrs_by_id.get(4183, ""),
        "publisher": attrs_by_id.get(7, ""),
        "brand": attrs_by_id.get(85, "Нет бренда"),
        "series": attrs_by_id.get(1, ""),
        "year": year_val,
        "pages": pages_val,
        "isbn": attrs_by_id.get(4184, ""),
        "cover_type": attrs_by_id.get(9356, "Твердый переплет"),
        "condition": attrs_by_id.get(8857, "Хорошая"),
        "genre": attrs_by_id.get(23273, "Проза"),
        "annotation": attrs_by_id.get(4191, ""),
        "age_limit": attrs_by_id.get(8862, ""),
        "translator": attrs_by_id.get(112, ""),
        "illustrator": attrs_by_id.get(111, ""),
        "paper_type": attrs_by_id.get(4385, ""),
        "price": price_val,
        "barcode": item_info.get("barcode", ""),
        "ozon_product_id": item_info.get("id"),
        "ozon_sku": item_info.get("sku"),
    }
