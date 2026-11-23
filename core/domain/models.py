"""
models.py: Типизированные доменные сущности (Book, PhotoItem, Dimensions).
Предотвращает ошибки Dict-Driven разработки и гарантирует типизацию во всей системе.
"""

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any, Dict, List, Optional

from core.domain.enums import AssetStatus, BookCondition, PhotoRole, TemplateMode
from core.domain.rules import (
    calculate_book_condition,
    calculate_gost_dimensions,
    clean_publisher_name,
    format_annotation_with_warning,
    normalize_author_name,
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
class AssetItem:
    """Модель ассета (фотокадра) в реестре SQLite."""
    id: str = ""
    book_id: Optional[int] = None
    book_article: Optional[str] = None
    slot: Optional[str] = None
    slot_order: int = 0
    status: AssetStatus = AssetStatus.UPLOADED
    status_message: str = ""
    original_path: str = ""
    preview_path: str = ""
    ai_white_path: Optional[str] = None
    final_render_path: Optional[str] = None
    transformations: Dict[str, Any] = field(default_factory=dict)
    s3_url: Optional[str] = None
    s3_etag: Optional[str] = None
    version: int = 1
    file_size_bytes: int = 0
    width: int = 0
    height: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssetItem":
        if not isinstance(data, dict):
            return cls()
        trans = data.get("transformations")
        if isinstance(trans, str):
            try:
                trans = json.loads(trans)
            except Exception:
                trans = {}
        elif not isinstance(trans, dict):
            trans = {}

        st = data.get("status") or AssetStatus.UPLOADED.value
        try:
            status_enum = AssetStatus(st)
        except Exception:
            status_enum = AssetStatus.UPLOADED

        return cls(
            id=str(data.get("id") or ""),
            book_id=int(data["book_id"]) if data.get("book_id") is not None else None,
            book_article=str(data.get("book_article") or "") if data.get("book_article") else None,
            slot=str(data.get("slot") or "") if data.get("slot") else None,
            slot_order=int(data.get("slot_order") or 0),
            status=status_enum,
            status_message=str(data.get("status_message") or ""),
            original_path=str(data.get("original_path") or ""),
            preview_path=str(data.get("preview_path") or ""),
            ai_white_path=data.get("ai_white_path"),
            final_render_path=data.get("final_render_path"),
            transformations=trans,
            s3_url=data.get("s3_url"),
            s3_etag=data.get("s3_etag"),
            version=int(data.get("version") or 1),
            file_size_bytes=int(data.get("file_size_bytes") or 0),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["status"] = self.status.value if hasattr(self.status, "value") else str(self.status)
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
        w = data.get("width") if (data.get("width") is not None and str(data.get("width")).strip() != "") else data.get("width_mm")
        l = data.get("length") if (data.get("length") is not None and str(data.get("length")).strip() != "") else data.get("length_mm")
        h = data.get("height") if (data.get("height") is not None and str(data.get("height")).strip() != "") else data.get("height_mm")
        wt = data.get("weight") if (data.get("weight") is not None and str(data.get("weight")).strip() != "") else data.get("weight_g")
        return cls(
            width_mm=int(w or 130),
            length_mm=int(l or 205),
            height_mm=int(h or 15),
            weight_g=int(wt or 250),
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
    width_package: Optional[int] = None
    length_package: Optional[int] = None
    height_package: Optional[int] = None
    weight_package: Optional[int] = None
    auto_package_adder: bool = True
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

        # Разбор габаритов (поддерживаем оба формата: width/weight и width_mm/weight_g)
        raw_w = data.get("width") if (data.get("width") is not None and str(data.get("width")).strip() != "") else data.get("width_mm")
        raw_l = data.get("length") if (data.get("length") is not None and str(data.get("length")).strip() != "") else data.get("length_mm")
        raw_h = data.get("height") if (data.get("height") is not None and str(data.get("height")).strip() != "") else data.get("height_mm")
        raw_wt = data.get("weight") if (data.get("weight") is not None and str(data.get("weight")).strip() != "") else data.get("weight_g")

        # Если передана строка dimensions вида "140х215х22" (игнорируя "[object")
        raw_dims_str = data.get("dimensions")
        if isinstance(raw_dims_str, str) and "[object" not in raw_dims_str and any(sep in raw_dims_str for sep in ("х", "x", "X", "Х", "*", "×", "/")):
            parts = [int(p.strip()) for p in re.split(r"[хxXХ*×/]", raw_dims_str) if p.strip().isdigit()]
            if len(parts) >= 3:
                if raw_w is None or int(raw_w or 0) <= 0: raw_w = parts[0]
                if raw_l is None or int(raw_l or 0) <= 0: raw_l = parts[1]
                if raw_h is None or int(raw_h or 0) <= 0: raw_h = parts[2]

        dims_data = {
            "width_mm": raw_w,
            "length_mm": raw_l,
            "height_mm": raw_h,
            "weight_g": raw_wt,
            "book_format_code": data.get("book_format_code"),
        }
        # Если было вложено в поле "dimensions" в виде словаря
        if isinstance(data.get("dimensions"), dict):
            dims_data.update(data["dimensions"])

        # Упаковочные габариты
        width_package = data.get("width_package")
        length_package = data.get("length_package")
        height_package = data.get("height_package")
        weight_package = data.get("weight_package")
        auto_package_adder = data.get("auto_package_adder")
        if auto_package_adder is None:
            auto_package_adder = True

        # Определение режима шаблона Ozon (фактический год издания имеет наивысший приоритет)
        mode_val = data.get("template_mode")
        if year_val:
            template_mode = resolve_template_mode(year_val)
        elif mode_val:
            template_mode = TemplateMode.POST2011 if str(mode_val).lower() in ("post2011", "post") else TemplateMode.PRE2011
        else:
            template_mode = TemplateMode.PRE2011

        return cls(
            article=str(data.get("article") or "").strip(),
            title=str(data.get("title") or "Без названия").strip(),
            original_title=str(data.get("original_title") or "").strip(),
            author=normalize_author_name(data.get("author")),
            author_cover=normalize_author_name(data.get("author_cover")),
            publisher=clean_publisher_name(data.get("publisher")),
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
            width_package=int(width_package) if width_package is not None else None,
            length_package=int(length_package) if length_package is not None else None,
            height_package=int(height_package) if height_package is not None else None,
            weight_package=int(weight_package) if weight_package is not None else None,
            auto_package_adder=bool(auto_package_adder),
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
        self.annotation = format_annotation_with_warning(self.annotation, has_def, self.condition)

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
        w = int(self.dimensions.width_mm or 130)
        l = int(self.dimensions.length_mm or 205)
        h = int(self.dimensions.height_mm or 15)
        wt = int(self.dimensions.weight_g or 250)
        d["width"] = w
        d["length"] = l
        d["height"] = h
        d["weight"] = wt
        d["width_mm"] = w
        d["length_mm"] = l
        d["height_mm"] = h
        d["weight_g"] = wt
        is_adder = self.auto_package_adder is not False
        w_pkg = int(self.width_package if self.width_package is not None else ((w + 10) if is_adder else w))
        l_pkg = int(self.length_package if self.length_package is not None else ((l + 10) if is_adder else l))
        h_pkg = int(self.height_package if self.height_package is not None else ((h + 10) if is_adder else h))
        wt_pkg = int(self.weight_package if self.weight_package is not None else ((wt + 30) if is_adder else wt))
        d["width_package"] = w_pkg
        d["length_package"] = l_pkg
        d["height_package"] = h_pkg
        d["weight_package"] = wt_pkg
        d["dimensions"] = f"{w_pkg}х{l_pkg}х{h_pkg}"
        d["auto_package_adder"] = is_adder
        return d
