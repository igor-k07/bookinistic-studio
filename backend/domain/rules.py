"""Pure domain rules, formulas, and normalization utilities.

Pure Python stdlib only (ADR-3). Zero external dependencies.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from backend.domain.enums import BookCondition, BookEra

WARNING_DEFECT_PREFIX = (
    "ВНИМАНИЕ! КНИГА НЕ НОВАЯ. Имеются определённые нюансы (повреждения) см. дополнительные фото."
)

SOVIET_FORMAT_MAP: Dict[str, Tuple[int, int]] = {
    "70x100/16": (176, 235),
    "70x90/16": (170, 215),
    "70x108/16": (170, 260),
    "84x108/16": (205, 260),
    "60x90/16": (145, 215),
    "60x84/16": (145, 200),
    "84x108/32": (130, 200),
    "70x108/32": (130, 165),
    "70x100/32": (120, 165),
    "70x90/32": (110, 165),
    "60x90/32": (107, 140),
    "60x84/32": (100, 140),
}

PAPER_DENSITIES_G_M2 = {
    "coated": 115,       # Мелованная
    "offset": 80,        # Офсетная (стандарт)
    "typographic": 65,   # Типографская / пухлая
    "newsprint": 50,     # Газетная
}


def resolve_book_era(year_val: Any) -> BookEra:
    """Determine Ozon template era boundary according to ADR-4.

    - PRE2011: year <= 2010 or year is None (antique/bukinistic)
    - POST2011: year >= 2011 (modern editions)
    """
    if not year_val:
        return BookEra.PRE2011
    try:
        y_str = str(year_val).strip()
        matches = re.findall(r"\d{4}", y_str)
        if matches:
            year_int = int(matches[0])
            return BookEra.PRE2011 if year_int <= 2010 else BookEra.POST2011
    except (ValueError, TypeError):
        pass
    return BookEra.PRE2011


def calculate_book_condition(
    has_defects: bool, manual_condition: Optional[str] = None
) -> BookCondition:
    """Determine book condition respecting manual grades and defect flags."""
    manual_norm = (manual_condition or "").strip().lower()
    if "удовл" in manual_norm:
        return BookCondition.SATISFACTORY
    if "плох" in manual_norm:
        return BookCondition.POOR
    if "хор" in manual_norm and "очень" not in manual_norm:
        return BookCondition.GOOD
    if "нов" in manual_norm and "как" not in manual_norm:
        return BookCondition.NEW
    if "как нов" in manual_norm:
        return BookCondition.FINE

    return BookCondition.GOOD if has_defects else BookCondition.VERY_GOOD


def format_annotation_with_warning(
    annotation: str,
    has_defects: bool,
    condition: Optional[str] = None,
) -> str:
    """Format book description with defect warning when applicable without duplication."""
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


def parse_format_code(text: str) -> Optional[Tuple[str, int, int]]:
    """Recognize typographic format code from text (e.g. '84x108/32')."""
    if not text:
        return None

    pattern = r"(\d{2,3})\s*[xх*×]\s*(\d{2,3})\s*(?:(?:1/|/)\s*(\d{1,2}))"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        w_sheet, l_sheet, fraction = m.group(1), m.group(2), m.group(3)
        key = f"{w_sheet}x{l_sheet}/{fraction}".lower()
        if key in SOVIET_FORMAT_MAP:
            w, length = SOVIET_FORMAT_MAP[key]
            return key, w, length

    m_direct = re.search(r"(\d{2,3})\s*[xх*×]\s*(\d{2,3})\s*(?:мм|mm)?", text, re.IGNORECASE)
    if m_direct:
        w = int(m_direct.group(1))
        length = int(m_direct.group(2))
        if 80 <= w <= 350 and 100 <= length <= 450:
            if w > length:
                w, length = length, w
            return f"{w}x{length}", w, length
    return None


def calculate_physical_dimensions(
    format_code: str = "",
    pages: int = 0,
    cover_type: str = "Твердый переплет",
    existing_dimensions: Optional[Dict[str, Any]] = None,
    allow_overwrite_manual: bool = False,
    paper_type: str = "offset",
) -> Dict[str, Any]:
    """Calculate dimensions and weight according to GOST physics (ADR-5).

    Fixes dust-jacket bug ('суперобложка' must not be classified as softcover).
    Safely parses string/float inputs in existing_dimensions.
    """
    existing = existing_dimensions or {}

    def _safe_pos_int(val: Any) -> Optional[int]:
        if val is None or str(val).strip() == "":
            return None
        try:
            parsed = int(float(str(val).strip()))
            return parsed if parsed > 0 else None
        except (ValueError, TypeError):
            return None

    raw_w = _safe_pos_int(existing.get("width") or existing.get("width_mm"))
    raw_l = _safe_pos_int(existing.get("length") or existing.get("length_mm"))
    raw_h = _safe_pos_int(existing.get("height") or existing.get("height_mm"))
    raw_wt = _safe_pos_int(existing.get("weight") or existing.get("weight_g"))

    width = 130
    length = 205
    fmt_key = ""

    parsed = parse_format_code(format_code)
    if parsed:
        fmt_key, width, length = parsed

    pages_int = max(0, int(pages or 0))
    cover_lower = (cover_type or "").lower()

    # Dust-jacket ("суперобложка") has a hard cover underneath
    is_dust_jacket = "супероблож" in cover_lower
    is_soft = ("мягк" in cover_lower or "облож" in cover_lower) and not is_dust_jacket

    cover_add = 4 if is_soft else 6
    spine = round(pages_int * 0.048 + cover_add)
    spine = max(4, min(spine, 150)) if pages_int > 0 else 15

    # Weight formula based on format and pages
    if fmt_key in ("70x100/16", "70x90/16"):
        calc_weight = round(pages_int * 0.95 + (70 if is_soft else 140))
    elif fmt_key == "60x90/16":
        calc_weight = round(pages_int * 0.70 + (50 if is_soft else 90))
    elif fmt_key in ("70x108/32", "70x100/32", "60x90/32", "60x84/32"):
        calc_weight = round(pages_int * 0.45 + (30 if is_soft else 60))
    else:
        calc_weight = round(pages_int * 0.65 + (40 if is_soft else 80))

    calc_weight = max(50, min(calc_weight, 5000)) if pages_int > 0 else 250

    fin_w = raw_w if (raw_w is not None and not allow_overwrite_manual) else width
    fin_l = raw_l if (raw_l is not None and not allow_overwrite_manual) else length
    fin_h = raw_h if (raw_h is not None and not allow_overwrite_manual) else spine
    fin_wt = raw_wt if (raw_wt is not None and not allow_overwrite_manual) else calc_weight

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


def clean_publisher_name(publisher_str: Any) -> str:
    """Clean publisher name stripping standard prefixes without mangling words like 'Идея-Пресс'."""
    if not publisher_str:
        return ""
    text = str(publisher_str).strip()
    if not text or text.lower() in ("none", "null", "не указано", "не указан"):
        return ""

    prefix_pattern = (
        r"^(?:государственное\s+)?"
        r"(?:издательство|изд-во|изд\.|издательский дом|издательская группа|издательский центр|"
        r"(?:ид|иг)(?:\s+|[:\-–—]))"
        r"\s*[:\-–—]?\s*"
    )
    text = re.sub(prefix_pattern, "", text, flags=re.IGNORECASE).strip()

    suffix_pattern = r"\s+(?:государственное\s+)?(?:издательство|изд-во|изд\.)$"
    text = re.sub(suffix_pattern, "", text, flags=re.IGNORECASE).strip()

    if (
        (text.startswith("«") and text.endswith("»"))
        or (text.startswith('"') and text.endswith('"'))
        or (text.startswith("'") and text.endswith("'"))
    ):
        text = text[1:-1].strip()

    return text


def normalize_author_name(author_str: Any) -> str:
    """Normalize author: if missing or unknown, return canonical 'не указан'."""
    if not author_str:
        return "не указан"
    s = str(author_str).strip()
    if not s or s.lower() in (
        "автор не указан", "не указан", "нет автора", "неизвестен", "none", "null", "—", "-"
    ):
        return "не указан"
    return s


def normalize_genre(genre_str: Any) -> str:
    """Normalize genre string."""
    if not genre_str:
        return ""
    return str(genre_str).strip()


def get_canonical_photo_filename(slot: str, index: int = 1, is_multi: bool = False) -> str:
    """Return standard canonical filename for asset export."""
    s = (slot or "").strip().lower()
    if s in ("cover_front", "front", "обложка", "лицевая", "slot_1"):
        return "01_cover_front.jpg"
    if s in ("mantra_defects", "defect", "damage", "дефект", "нюанс", "slot_4", "slot_5"):
        return f"02_defect_{index}.jpg"
    if s in ("illustrations", "illustration", "иллюстрация", "рисунок", "slot_5", "slot_6"):
        return f"03_illustration_{index}.jpg"
    if s in ("cover_back", "back", "задник", "оборот", "slot_2"):
        return f"04_cover_back_{index}.jpg" if (is_multi or index > 1) else "04_cover_back.jpg"
    if s in ("info_pages", "info_page", "title_page", "colophon", "титул", "титульный", "колофон", "slot_3"):
        return f"info_page_{index}.jpg"
    if s in ("card", "promo", "promo_card", "карточка", "99_card"):
        return "99_card.jpg"
    return f"photo_{index}.jpg"


def classify_filename_to_slot(filename_or_url: str) -> str:
    """Classify photo filename or URL to slot with token boundary matching."""
    if not filename_or_url:
        return "other"

    clean_target = str(filename_or_url).split("?")[0].split("#")[0]
    base = clean_target.rstrip("/").split("/")[-1].lower()
    if not base:
        return "other"

    if base in ("cover_front", "cover_back", "info_pages", "illustrations", "mantra_defects"):
        return base

    # Token boundary matching helpers
    def _has_token(word: str) -> bool:
        return bool(re.search(rf"(?:^|[\W_]){re.escape(word)}(?:[\W_]|$)", base))

    if _has_token("card") or base == "99_card.jpg":
        return "card"

    if any(_has_token(t) for t in ("defect", "damage", "дефект", "нюанс", "mantra")):
        return "mantra_defects"

    if any(_has_token(t) for t in ("cover_back", "back", "задник", "оборот")):
        return "cover_back"

    if any(_has_token(t) for t in ("info", "title", "colophon", "титул", "колофон")):
        return "info_pages"

    if any(_has_token(t) for t in ("front", "cover", "обложка", "лицевая")) or base.startswith("01_"):
        return "cover_front"

    if any(_has_token(t) for t in ("illustration", "иллюстрация", "рисунок", "иллюстрац")):
        return "illustrations"

    if any(base.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
        return "illustrations"

    return "other"


# Aliases for consistent naming
normalize_photo_role = classify_filename_to_slot
determine_book_era = resolve_book_era
calculate_dimensions_and_weight = calculate_physical_dimensions


def merge_field_value(
    field_name: str,
    current_value: Any,
    current_source: Any,
    incoming_value: Any,
    incoming_source: Any,
) -> Tuple[Any, Any]:
    """Merge incoming field value according to FieldProvenance priority (ADR-8).

    Priority: EMPTY(0) < DEFAULT(1) < AI_GEMINI(2) < DB_CANONICAL(3) < FANTLAB_EXACT(4) < USER_MANUAL(5).
    USER_MANUAL is strictly protected and never overwritten.
    """
    if incoming_value is None or incoming_value == "":
        return current_value, current_source

    curr_prio = int(current_source) if current_source is not None else 0
    inc_prio = int(incoming_source) if incoming_source is not None else 0

    if inc_prio > curr_prio:
        return incoming_value, incoming_source

    if inc_prio == curr_prio:
        if current_value is None or current_value == "" or current_value == 0:
            return incoming_value, incoming_source

    return current_value, current_source
