"""
rules.py: Чистые доменные бизнес-правила и формулы Bookinistic Studio.
Не зависят от внешних библиотек, БД, сети или файловой системы.
"""

import re
from typing import Any, Dict, Optional, Tuple

from core.domain.enums import BookCondition, TemplateMode

WARNING_DEFECT_PREFIX = "ВНИМАНИЕ! КНИГА НЕ НОВАЯ. Имеются определённые нюансы (повреждения) см. дополнительные фото."

# Справочник стандартных типографских форматов советских и российских книг (доля листа -> Ш х Д в мм)
SOVIET_FORMAT_MAP = {
    # Большие / энциклопедические форматы
    "70x100/16": (176, 235), # 175-176 x 235-240 мм (детские книги, альбомы, энциклопедии)
    "70x90/16": (170, 215),  # Увеличенный широкий
    "70x108/16": (170, 260), # Академический
    "84x108/16": (205, 260), # Альбомный / подарочный
    # Увеличенные форматы
    "60x90/16": (145, 215),  # Самый частый увеличенный формат
    "60x84/16": (145, 200),  # Самый массовый стандарт советской книги
    # Стандартные форматы
    "84x108/32": (130, 200), # Типовой формат художественной литературы (130x205)
    # Малые / карманные форматы
    "70x108/32": (130, 165), # Малый стандарт
    "70x100/32": (120, 165), # Малый
    "70x90/32": (110, 165),  # Карманный стандарт
    "60x90/32": (107, 140),  # Карманный покетбук
    "60x84/32": (100, 140),  # Карманный малый
}


def calculate_book_condition(has_defects: bool, manual_condition: Optional[str] = None) -> BookCondition:
    """
    Рассчитывает сохранность книги по правилам спецификации (п. 5.3):
    1. Нет дефектов -> 'Очень хорошая'
    2. Есть дефекты -> 'Хорошая'
    3. 'Удовлетворительная'/'Плохая' выставляется ТОЛЬКО вручную букинистом.
    """
    manual_norm = (manual_condition or "").strip().lower()
    if "удовл" in manual_norm:
        return BookCondition.SATISFACTORY
    if "плох" in manual_norm:
        return BookCondition.BAD

    if not has_defects:
        return BookCondition.VERY_GOOD
    return BookCondition.GOOD


def format_annotation_with_warning(annotation: str, has_defects: bool) -> str:
    """
    Форматирует аннотацию:
    - Добавляет предупреждение о нюансах, ТОЛЬКО если есть дефекты.
    - Удаляет предупреждение, если дефектов нет.
    - Исключает дублирование префикса.
    """
    text = (annotation or "").strip()
    if WARNING_DEFECT_PREFIX in text:
        text = text.replace(WARNING_DEFECT_PREFIX, "").strip()

    if has_defects and text:
        return f"{WARNING_DEFECT_PREFIX}\n\n{text}".strip()
    return text


def resolve_template_mode(year_val: Any) -> TemplateMode:
    """
    Определяет шаблон Ozon (до 2011 / после 2011) по году издания книги.
    """
    if not year_val:
        return TemplateMode.PRE2011
    try:
        y_str = str(year_val).strip()
        m = re.findall(r"\d{4}", y_str)
        if m:
            y_int = int(m[0])
            return TemplateMode.PRE2011 if y_int <= 2011 else TemplateMode.POST2011
    except Exception:
        pass
    return TemplateMode.PRE2011


def parse_format_code(text: str) -> Optional[Tuple[str, int, int]]:
    """
    Распознает типографский формат из строки (например '84x108/32', '70x100 1/16').
    Возвращает (format_key, width_mm, length_mm) или None.
    """
    if not text:
        return None
    m = re.search(r'(\d{2,3})\s*[xх*×]\s*(\d{2,3})\s*(?:(?:1/|/)\s*(\d{1,2}))', text, re.IGNORECASE)
    if m:
        w_sheet, l_sheet, fraction = m.group(1), m.group(2), m.group(3)
        key = f"{w_sheet}x{l_sheet}/{fraction}".lower()
        if key in SOVIET_FORMAT_MAP:
            w, l = SOVIET_FORMAT_MAP[key]
            return key, w, l

    # Поиск прямого указания размеров '130x200 мм'
    m_direct = re.search(r'(\d{2,3})\s*[xх*×]\s*(\d{2,3})\s*(?:мм|mm)?', text, re.IGNORECASE)
    if m_direct:
        w = int(m_direct.group(1))
        l = int(m_direct.group(2))
        if 80 <= w <= 350 and 100 <= l <= 450:
            if w > l:
                w, l = l, w
            return f"{w}x{l}", w, l
    return None


def calculate_gost_dimensions(
    format_code: str = "",
    pages: int = 0,
    cover_type: str = "Твердый переплет",
    existing_dimensions: Optional[Dict[str, Any]] = None,
    allow_overwrite_manual: bool = False,
) -> Dict[str, Any]:
    """
    Рассчитывает габариты и вес по ГОСТ-формулам (п. 5.2 спецификации).
    Принцип независимости: если пользователь уже ввёл габариты вручную,
    они НЕ перезаписываются при автоматических пересчетах, если allow_overwrite_manual=False.
    """
    existing = existing_dimensions or {}
    has_manual_w = bool(existing.get("width_mm") and int(existing.get("width_mm", 0)) > 0)
    has_manual_l = bool(existing.get("length_mm") and int(existing.get("length_mm", 0)) > 0)
    has_manual_h = bool(existing.get("height_mm") and int(existing.get("height_mm", 0)) > 0)
    has_manual_weight = bool(existing.get("weight_g") and int(existing.get("weight_g", 0)) > 0)

    # Стандартные базовые размеры (художественная книга 84x108/32)
    width = 130
    length = 205
    fmt_key = ""

    parsed = parse_format_code(format_code)
    if parsed:
        fmt_key, width, length = parsed

    # Расчет толщины корешка
    pages_int = max(0, int(pages or 0))
    is_soft = "мягк" in (cover_type or "").lower() or "обложка" in (cover_type or "").lower()
    cover_add = 4 if is_soft else 6
    spine = round(pages_int * 0.048 + cover_add)
    spine = max(4, min(spine, 150)) if pages_int > 0 else 15

    # Расчет веса
    if fmt_key == "70x100/16" or fmt_key == "70x90/16":
        weight = round(pages_int * 0.95 + (70 if is_soft else 140))
    elif fmt_key == "60x90/16":
        weight = round(pages_int * 0.70 + (50 if is_soft else 90))
    elif fmt_key in ("70x108/32", "70x100/32", "60x90/32", "60x84/32"):
        weight = round(pages_int * 0.45 + (30 if is_soft else 60))
    else:
        weight = round(pages_int * 0.65 + (40 if is_soft else 80))

    weight = max(50, min(weight, 5000)) if pages_int > 0 else 250

    return {
        "book_format_code": fmt_key or format_code,
        "width_mm": existing.get("width_mm") if (has_manual_w and not allow_overwrite_manual) else width,
        "length_mm": existing.get("length_mm") if (has_manual_l and not allow_overwrite_manual) else length,
        "height_mm": existing.get("height_mm") if (has_manual_h and not allow_overwrite_manual) else spine,
        "weight_g": existing.get("weight_g") if (has_manual_weight and not allow_overwrite_manual) else weight,
    }

