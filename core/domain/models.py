"""
models.py: Типизированные доменные сущности (Book, PhotoItem, Dimensions).
Предотвращает ошибки Dict-Driven разработки и гарантирует типизацию во всей системе.
"""

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any, Dict, List, Optional

from core.domain.enums import BookCondition, PhotoRole, TemplateMode
from core.domain.rules import (
    calculate_book_condition,
    calculate_gost_dimensions,
    format_annotation_with_warning,
    resolve_template_mode,
)


@dataclass
class PhotoItem:
    """Модель одного фотокадра книги."""
    id: str = ""
    role: PhotoRole = PhotoRole.OTHER
    filename: str = "photo.jpg"
    data: Optional[str] = None         # Base64 строка (для передачи из UI)
    preview: Optional[str] = None      # Data-URL превью
    url: Optional[str] = None          # Относительный или локальный URL
    s3_url: Optional[str] = None       # Постоянная ссылка Yandex S3 CDN
    local_path: Optional[str] = None   # Абсолютный путь на диске Mac
    is_temporary: bool = True          # Подлежит ли авто-очистке после выгрузки в S3
    crop_relative: Optional[Dict[str, float]] = None
    rotation: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any], default_role: PhotoRole = PhotoRole.OTHER) -> "PhotoItem":
        if not isinstance(data, dict):
            return cls(role=default_role)
        role_raw = data.get("role") or data.get("role_name") or default_role.value
        role = PhotoRole.from_str(str(role_raw))
        return cls(
            id=str(data.get("id") or ""),
            role=role,
            filename=str(data.get("name") or data.get("filename") or "photo.jpg"),
            data=data.get("data"),
            preview=data.get("preview"),
            url=data.get("url"),
            s3_url=data.get("s3_url"),
            local_path=data.get("local_path"),
            is_temporary=bool(data.get("is_temporary", True)),
            crop_relative=data.get("crop_relative"),
            rotation=int(data.get("rotation", 0)),
        )

    def to_dict(self, include_base64: bool = True) -> Dict[str, Any]:
        res = asdict(self)
        res["role"] = self.role.value
        if not include_base64:
            res.pop("data", None)
            res.pop("preview", None)
        return res


@dataclass
class Dimensions:
    """Габариты и вес книги."""
    width_mm: int = 130
    length_mm: int = 205
    height_mm: int = 15
    weight_g: int = 250
    book_format_code: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Dimensions":
        if not isinstance(data, dict):
            return cls()
        return cls(
            width_mm=int(data.get("width_mm") or 130),
            length_mm=int(data.get("length_mm") or 205),
            height_mm=int(data.get("height_mm") or 15),
            weight_g=int(data.get("weight_g") or 250),
            book_format_code=str(data.get("book_format_code") or "").strip(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Book:
    """
    Основная доменная сущность книги букинистического магазина.
    """
    article: str = ""
    title: str = "Без названия"
    original_title: str = ""
    author: str = ""              # Паспортный формат: 'Фамилия Имя Отчество'
    author_cover: str = ""        # Как на обложке: 'Имя Фамилия'
    publisher: str = ""
    brand: str = "Нет бренда"
    year: Optional[int] = None
    pages: Optional[int] = None
    isbn: str = ""
    isbn_100_percent_on_photo: bool = False
    barcode: str = ""
    cover_type: str = "Твердый переплет"
    condition: str = BookCondition.VERY_GOOD.value
    genre: str = "Проза"
    paper_type: str = ""
    age_limit: str = ""
    annotation: str = ""
    translator: str = ""
    illustrator: str = ""
    price: Optional[float] = None
    dimensions: Dimensions = field(default_factory=Dimensions)
    template_mode: TemplateMode = TemplateMode.PRE2011
    status: str = "ready"
    slots_photos: Dict[str, Any] = field(default_factory=dict)
    main_photo_url: str = ""
    add_photo_urls: str = ""
    vault_folder: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Book":
        """Создает экземпляр Book из любого произвольного словаря UI, БД или ИИ."""
        if not isinstance(data, dict):
            return cls()

        # Разбор года
        year_val = None
        raw_year = data.get("year")
        if raw_year is not None:
            m = re.findall(r"\d{4}", str(raw_year))
            if m:
                year_val = int(m[0])

        # Разбор страниц
        pages_val = None
        raw_pages = data.get("pages")
        if raw_pages is not None:
            m_p = re.findall(r"\d+", str(raw_pages))
            if m_p:
                pages_val = int(m_p[0])

        # Разбор цены
        price_val = None
        raw_price = data.get("price")
        if raw_price is not None and str(raw_price).strip():
            clean_p = re.sub(r"[^\d.,]", "", str(raw_price)).replace(",", ".")
            if clean_p:
                try:
                    price_val = float(clean_p)
                except Exception:
                    pass

        # Разбор габаритов
        dims_data = {
            "width_mm": data.get("width_mm"),
            "length_mm": data.get("length_mm"),
            "height_mm": data.get("height_mm"),
            "weight_g": data.get("weight_g"),
            "book_format_code": data.get("book_format_code"),
        }
        # Если было вложено в поле "dimensions"
        if isinstance(data.get("dimensions"), dict):
            dims_data.update(data["dimensions"])

        # Определение режима шаблона Ozon
        mode_val = data.get("template_mode")
        if not mode_val:
            template_mode = resolve_template_mode(year_val)
        else:
            template_mode = TemplateMode.POST2011 if str(mode_val).lower() in ("post2011", "post") else TemplateMode.PRE2011

        return cls(
            article=str(data.get("article") or "").strip(),
            title=str(data.get("title") or "Без названия").strip(),
            original_title=str(data.get("original_title") or "").strip(),
            author=str(data.get("author") or "").strip(),
            author_cover=str(data.get("author_cover") or "").strip(),
            publisher=str(data.get("publisher") or "").strip(),
            brand=str(data.get("brand") or "Нет бренда").strip(),
            year=year_val,
            pages=pages_val,
            isbn=str(data.get("isbn") or "").strip(),
            isbn_100_percent_on_photo=bool(data.get("isbn_100_percent_on_photo", False)),
            barcode=str(data.get("barcode") or "").strip(),
            cover_type=str(data.get("cover_type") or "Твердый переплет").strip(),
            condition=str(data.get("condition") or BookCondition.VERY_GOOD.value).strip(),
            genre=str(data.get("genre") or "Проза").strip(),
            paper_type=str(data.get("paper_type") or "").strip(),
            age_limit=str(data.get("age_limit") or "").strip(),
            annotation=str(data.get("annotation") or "").strip(),
            translator=str(data.get("translator") or "").strip(),
            illustrator=str(data.get("illustrator") or "").strip(),
            price=price_val,
            dimensions=Dimensions.from_dict(dims_data),
            template_mode=template_mode,
            status=str(data.get("status") or "ready"),
            slots_photos=data.get("slots_photos") or {},
            main_photo_url=str(data.get("main_photo_url") or "").strip(),
            add_photo_urls=str(data.get("add_photo_urls") or "").strip(),
            vault_folder=str(data.get("vault_folder") or "").strip(),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def has_defects(self) -> bool:
        """Определяет, есть ли у книги фото дефектов (в слоте 5)."""
        if not self.slots_photos or not isinstance(self.slots_photos, dict):
            return False
        # Проверяем возможные имена слота дефектов
        defects = (
            self.slots_photos.get("mantra_defects")
            or self.slots_photos.get("defects")
            or self.slots_photos.get("defect")
            or []
        )
        if isinstance(defects, list):
            return len(defects) > 0
        if isinstance(defects, dict):
            return bool(defects.get("data") or defects.get("url") or defects.get("name"))
        return False

    def sanitize_domain_rules(self, allow_overwrite_manual_dims: bool = False) -> None:
        """
        Применяет чистые доменные правила ко всем полям книги:
        - Вычисляет сохранность (Очень хорошая / Хорошая / сохраняет ручную Удовлетворительную)
        - Добавляет/удаляет предупреждение о нюансах в аннотации
        - Рассчитывает габариты и вес с защитой ручных правок пользователя
        """
        has_def = self.has_defects()
        # 1. Сохранность
        self.condition = calculate_book_condition(has_def, self.condition).value

        # 2. Аннотация
        self.annotation = format_annotation_with_warning(self.annotation, has_def)

        # 3. Габариты и вес (ГОСТ)
        calculated_dims = calculate_gost_dimensions(
            format_code=self.dimensions.book_format_code,
            pages=self.pages or 0,
            cover_type=self.cover_type,
            existing_dimensions=self.dimensions.to_dict(),
            allow_overwrite_manual=allow_overwrite_manual_dims,
        )
        self.dimensions = Dimensions.from_dict(calculated_dims)

    def to_dict(self) -> Dict[str, Any]:
        """Возвращает плоский словарь для фронтенда и API."""
        d = asdict(self)
        d["template_mode"] = self.template_mode.value
        # Разворачиваем габариты на верхний уровень для совместимости с UI
        d.update(self.dimensions.to_dict())
        return d
