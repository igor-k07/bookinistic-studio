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
    if "хор" in manual_norm and "очень" not in manual_norm:
        return BookCondition.GOOD

    if not has_defects:
        return BookCondition.VERY_GOOD
    return BookCondition.GOOD


def format_annotation_with_warning(
    annotation: str,
    has_defects: bool,
    condition: Optional[str] = None
) -> str:
    """
    Форматирует аннотацию:
    - Добавляет предупреждение о нюансах, если есть дефекты ИЛИ состояние ухудшено вручную (Хорошая/Удовлетворительная).
    - Удаляет предупреждение, если дефектов нет и состояние Очень хорошая.
    - Исключает дублирование префикса.
    """
    text = (annotation or "").strip()
    if WARNING_DEFECT_PREFIX in text:
        text = text.replace(WARNING_DEFECT_PREFIX, "").strip()

    cond_norm = (condition or "").strip().lower()
    should_warn = (
        has_defects
        or ("хор" in cond_norm and "очень" not in cond_norm)
        or ("удовл" in cond_norm)
        or ("плох" in cond_norm)
    )

    if should_warn and text:
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
    raw_w = existing.get("width") if (existing.get("width") is not None and str(existing.get("width")).strip() != "") else existing.get("width_mm")
    raw_l = existing.get("length") if (existing.get("length") is not None and str(existing.get("length")).strip() != "") else existing.get("length_mm")
    raw_h = existing.get("height") if (existing.get("height") is not None and str(existing.get("height")).strip() != "") else existing.get("height_mm")
    raw_wt = existing.get("weight") if (existing.get("weight") is not None and str(existing.get("weight")).strip() != "") else existing.get("weight_g")

    has_manual_w = bool(raw_w and int(raw_w) > 0)
    has_manual_l = bool(raw_l and int(raw_l) > 0)
    has_manual_h = bool(raw_h and int(raw_h) > 0)
    has_manual_weight = bool(raw_wt and int(raw_wt) > 0)

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

    fin_w = int(raw_w) if (has_manual_w and not allow_overwrite_manual) else width
    fin_l = int(raw_l) if (has_manual_l and not allow_overwrite_manual) else length
    fin_h = int(raw_h) if (has_manual_h and not allow_overwrite_manual) else spine
    fin_wt = int(raw_wt) if (has_manual_weight and not allow_overwrite_manual) else weight

    return {
        "book_format_code": fmt_key or format_code,
        "width_mm": fin_w,
        "length_mm": fin_l,
        "height_mm": fin_h,
        "weight_g": fin_wt,
        "width": fin_w,
        "length": fin_l,
        "height": fin_h,
        "weight": fin_wt,
    }


# Идентификаторы слотов книги
SLOT_COVER_FRONT = "cover_front"
SLOT_COVER_BACK = "cover_back"
SLOT_INFO_PAGES = "info_pages"
SLOT_ILLUSTRATIONS = "illustrations"
SLOT_DEFECTS = "mantra_defects"
SLOT_CARD = "card"


def get_canonical_photo_filename(slot: str, index: int = 1, is_multi: bool = False) -> str:
    """
    Возвращает каноническое имя файла для слота согласно регламенту Photo Pipeline:
    - cover_front -> '01_cover_front.jpg'
    - mantra_defects / defect -> '02_defect_{index}.jpg'
    - illustrations / illustration -> '03_illustration_{index}.jpg'
    - cover_back -> '04_cover_back_{index}.jpg' (или '04_cover_back.jpg' если одиночный)
    - info_pages / info_page -> 'info_page_{index}.jpg'
    - card -> '99_card.jpg'
    """
    s = (slot or "").strip().lower()
    if s in ("cover_front", "front", "обложка", "лицевая", "slot_1"):
        return "01_cover_front.jpg"
    if s in ("mantra_defects", "defect", "damage", "дефект", "нюанс", "slot_5"):
        return f"02_defect_{index}.jpg"
    if s in ("illustrations", "illustration", "иллюстрация", "рисунок", "slot_6"):
        return f"03_illustration_{index}.jpg"
    if s in ("cover_back", "back", "задник", "оборот", "slot_2"):
        return f"04_cover_back_{index}.jpg" if (is_multi or index > 1) else "04_cover_back.jpg"
    if s in ("info_pages", "info_page", "title_page", "colophon", "титул", "титульный", "колофон", "slot_3", "slot_4"):
        return f"info_page_{index}.jpg"
    if s in ("card", "promo", "promo_card", "карточка"):
        return "99_card.jpg"
    return f"photo_{index}.jpg"


def classify_filename_to_slot(filename_or_url: str) -> str:
    """
    Интеллектуально определяет слот книги по имени файла или URL (включая исторические Ozon ссылки).
    Поддерживает как эталонный формат (01_cover_front, 02_defect, 03_illustration, 04_cover_back),
    так и альтернативные схемы (02_cover_back, 04_illustration, 05_defect, info_page, 99_card).
    Возвращает один из:
    - 'cover_front'
    - 'cover_back'
    - 'info_pages'
    - 'illustrations'
    - 'mantra_defects'
    - 'card'
    - 'other'
    """
    if not filename_or_url:
        return "other"

    clean_target = str(filename_or_url).split("?")[0].split("#")[0]
    base = clean_target.rstrip("/").split("/")[-1].lower()

    if not base:
        return "other"

    # 1. Промо-карточка магазина
    if "card" in base:
        return SLOT_CARD

    # 2. Дефекты и повреждения (02_defect_*, 05_defect_*, defect_*, damage_*)
    if "defect" in base or "damage" in base or "дефект" in base or "нюанс" in base:
        return SLOT_DEFECTS

    # 3. Задняя обложка (04_cover_back, 02_cover_back, cover_back, back, задник)
    if "cover_back" in base or "back" in base or "задник" in base or "оборот" in base:
        return SLOT_COVER_BACK

    # 4. Информационные страницы (info_page, 03_info_page, title, colophon, титул)
    if "info" in base or "title" in base or "colophon" in base or "титул" in base or "колофон" in base:
        return SLOT_INFO_PAGES

    # 5. Лицевая обложка (01_cover_front, front, cover, обложка)
    if "front" in base or "cover" in base or base.startswith("01_") or "облож" in base or "лицев" in base:
        return SLOT_COVER_FRONT

    # 6. Иллюстрации (03_illustration, 04_illustration, illustration, рисунок)
    if "illustration" in base or "иллюстрац" in base or "рисунок" in base:
        return SLOT_ILLUSTRATIONS

    # 7. Для файлов с расширениями изображений по умолчанию иллюстрации
    if any(base.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
        return SLOT_ILLUSTRATIONS

    return "other"


def clean_publisher_name(publisher_str: Any) -> str:
    """
    Очищает название издательства от слова 'издательство', 'изд-во' и обрамляющих кавычек.
    Например:
      'Издательство «Наука»' -> 'Наука'
      'Изд-во Эксмо' -> 'Эксмо'
      'Издательский дом "Питер"' -> 'Питер'
    """
    if not publisher_str:
        return ""
    text = str(publisher_str).strip()
    if not text or text.lower() in ("none", "null", "не указано", "не указан"):
        return ""

    # Снятие префиксов 'государственное издательство', 'издательство', 'изд-во', 'изд.', 'издательский дом', 'ид', 'иг'
    prefix_pattern = r'^(?:государственное\s+)?(?:издательство|изд-во|изд\.|издательский дом|издательская группа|издательский центр|ид|иг)\s*[:\-–—]?\s*'
    text = re.sub(prefix_pattern, '', text, flags=re.IGNORECASE).strip()

    # Снятие суффиксов 'издательство', 'изд-во'
    suffix_pattern = r'\s+(?:государственное\s+)?(?:издательство|изд-во|изд\.)$'
    text = re.sub(suffix_pattern, '', text, flags=re.IGNORECASE).strip()

    # Снятие обрамляющих кавычек «...», "...", '...'
    if (text.startswith('«') and text.endswith('»')) or (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()

    return text


def normalize_author_name(author_str: Any) -> str:
    """
    Нормализует автора: по справочнику Ozon при отсутствии автора указывается строго 'не указан'.
    Заменяет 'Автор не указан', 'нет автора', 'неизвестен' и т.п. на 'не указан'.
    """
    if not author_str:
        return "не указан"
    s = str(author_str).strip()
    if not s or s.lower() in ("автор не указан", "не указан", "нет автора", "неизвестен", "none", "null", "—", "-"):
        return "не указан"
    return s



