"""
excel_service.py: Управление таблицами Excel (OpenXML) для Ozon (pre2011 и post2011).
"""

from datetime import datetime
from functools import wraps
import os
import re
import shutil
import threading
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
import zipfile
from typing import Any, Dict, List

from config import (
    BACKUP_FILE_POST2011,
    BACKUP_FILE_PRE2011,
    BASE_DIR,
    READY_TABLES_DIR,
    READY_TABLES_PRE2011_DIR,
    READY_TABLES_POST2011_DIR,
    VAULT_DIR,
    get_target_excel_file,
)
from core.barcode import generate_ean13_from_article
from core.constants import normalize_genre
from core.domain.rules import calculate_book_condition, clean_publisher_name, normalize_author_name
import services.tunnel_service as tunnel_service


# Межпоточный реентерабельный мьютекс для защиты целостности таблиц Excel Ozon
EXCEL_LOCK = threading.RLock()


def with_excel_lock(func):
    """Декоратор для безопасной многопоточной записи/чтения таблиц Excel Ozon."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with EXCEL_LOCK:
            return func(*args, **kwargs)
    return wrapper


def normalize_condition(raw_cond: Any, has_defects: bool) -> str:
    """Приводит сохранность книги к регламенту Ozon через единое доменное правило."""
    return calculate_book_condition(has_defects, str(raw_cond or "")).value


@with_excel_lock
def get_current_books(mode: str = "pre2011") -> List[Dict[str, Any]]:
    """Считывает все добавленные книги из таблицы (pre2011 или post2011)."""
    target_file = get_target_excel_file(mode)
    if not os.path.exists(target_file):
        return []

    try:
        with zipfile.ZipFile(target_file, "r") as z:
            s1 = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
            strings = [
                "".join(t.text for t in si.findall(".//ns:t", ns) if t.text)
                for si in sst.findall("ns:si", ns)
            ]

            books = []
            for r in s1.findall(".//ns:row", ns):
                r_num = int(r.attrib.get("r", "0"))
                if r_num < 5:
                    continue
                cells = {
                    "".join(ch for ch in c.attrib.get("r", "") if ch.isalpha()): c
                    for c in r.findall("ns:c", ns)
                }

                def get_val(col):
                    c = cells.get(col)
                    if c is None:
                        return ""
                    t = c.attrib.get("t")
                    if t == "inlineStr":
                        return "".join(c.findtext(".//ns:t", default="", namespaces=ns))
                    v = c.findtext("ns:v", default="", namespaces=ns)
                    return (
                        strings[int(v)]
                        if t == "s" and v.isdigit() and int(v) < len(strings)
                        else v
                    )

                art = get_val("B")
                title = get_val("C")
                if art.strip() or title.strip():
                    if mode == "pre2011":
                        w_pkg_raw = get_val("N")
                        h_pkg_raw = get_val("O")
                        l_pkg_raw = get_val("P")
                        wt_pkg_raw = get_val("M")
                        w_pkg = int(w_pkg_raw) if (w_pkg_raw and str(w_pkg_raw).isdigit()) else 140
                        h_pkg = int(h_pkg_raw) if (h_pkg_raw and str(h_pkg_raw).isdigit()) else 25
                        l_pkg = int(l_pkg_raw) if (l_pkg_raw and str(l_pkg_raw).isdigit()) else 215
                        wt_pkg = int(wt_pkg_raw) if (wt_pkg_raw and str(wt_pkg_raw).isdigit()) else 330
                        net_w = max(10, w_pkg - 10)
                        net_h = max(1, h_pkg - 10)
                        net_l = max(10, l_pkg - 10)
                        net_wt = max(10, wt_pkg - 30)

                        books.append({
                            "row": r_num,
                            "template_mode": "pre2011",
                            "num": get_val("A"),
                            "article": art,
                            "title": title,
                            "price": get_val("D"),
                            "old_price": get_val("E"),
                            "author_cover": get_val("T"),
                            "author": get_val("U"),
                            "publisher": get_val("AI"),
                            "year": get_val("AK"),
                            "condition": get_val("AS"),
                            "isbn": get_val("AR"),
                            "barcode": get_val("K"),
                            "genre": get_val("Z"),
                            "cover": get_val("V"),
                            "cover_type": get_val("V"),
                            "pages": get_val("AN"),
                            "brand": get_val("Y"),
                            "series": get_val("AJ"),
                            "annotation": get_val("AE"),
                            "illustrator": get_val("AG"),
                            "translator": get_val("AH"),
                            "target_audience": get_val("AB"),
                            "paper_type": get_val("AL"),
                            "dimensions": f"{w_pkg}х{l_pkg}х{h_pkg}",
                            "weight": net_wt,
                            "weight_package": wt_pkg,
                            "width": net_w,
                            "width_package": w_pkg,
                            "height": net_h,
                            "height_package": h_pkg,
                            "length": net_l,
                            "length_package": l_pkg,
                            "width_mm": net_w,
                            "height_mm": net_h,
                            "length_mm": net_l,
                            "weight_g": net_wt,
                            "age_limit": get_val("AT"),
                            "country": get_val("BZ"),
                            "original_title": get_val("BY"),
                            "collect_reviews": get_val("H") or "Нет",
                            "photo_main": get_val("Q"),
                            "main_photo_url": get_val("Q"),
                            "photos_additional": get_val("R"),
                            "add_photo_urls": get_val("R"),
                            "photo_article": get_val("S"),
                        })
                    else:
                        w_pkg_raw = get_val("M")
                        h_pkg_raw = get_val("N")
                        l_pkg_raw = get_val("O")
                        wt_pkg_raw = get_val("L")
                        w_pkg = int(w_pkg_raw) if (w_pkg_raw and str(w_pkg_raw).isdigit()) else 140
                        h_pkg = int(h_pkg_raw) if (h_pkg_raw and str(h_pkg_raw).isdigit()) else 25
                        l_pkg = int(l_pkg_raw) if (l_pkg_raw and str(l_pkg_raw).isdigit()) else 215
                        wt_pkg = int(wt_pkg_raw) if (wt_pkg_raw and str(wt_pkg_raw).isdigit()) else 330
                        net_w = max(10, w_pkg - 10)
                        net_h = max(1, h_pkg - 10)
                        net_l = max(10, l_pkg - 10)
                        net_wt = max(10, wt_pkg - 30)

                        books.append({
                            "row": r_num,
                            "template_mode": "post2011",
                            "num": get_val("A"),
                            "article": art,
                            "title": title,
                            "price": get_val("D"),
                            "old_price": get_val("E"),
                            "author_cover": get_val("S"),
                            "author": get_val("T"),
                            "publisher": "",
                            "year": get_val("AJ"),
                            "condition": get_val("AQ"),
                            "isbn": get_val("Y"),
                            "barcode": get_val("J"),
                            "genre": get_val("Z"),
                            "cover": get_val("U"),
                            "cover_type": get_val("U"),
                            "pages": get_val("AM"),
                            "brand": get_val("X"),
                            "series": get_val("AI"),
                            "annotation": get_val("AE"),
                            "illustrator": get_val("AG"),
                            "translator": get_val("AH"),
                            "target_audience": get_val("AB"),
                            "paper_type": get_val("AK"),
                            "dimensions": f"{w_pkg}х{l_pkg}х{h_pkg}",
                            "weight": net_wt,
                            "weight_package": wt_pkg,
                            "width": net_w,
                            "width_package": w_pkg,
                            "height": net_h,
                            "height_package": h_pkg,
                            "length": net_l,
                            "length_package": l_pkg,
                            "width_mm": net_w,
                            "height_mm": net_h,
                            "length_mm": net_l,
                            "weight_g": net_wt,
                            "age_limit": get_val("AR"),
                            "country": get_val("CE"),
                            "original_title": get_val("CD"),
                            "collect_reviews": get_val("H") or "Нет",
                            "photo_main": get_val("P"),
                            "main_photo_url": get_val("P"),
                            "photos_additional": get_val("Q"),
                            "add_photo_urls": get_val("Q"),
                            "photo_article": get_val("R"),
                        })
            return books
    except Exception as e:
        print(f"Ошибка чтения книг из batch excel ({mode}):", e)
        return []


@with_excel_lock
def append_book_to_excel(b: Dict[str, Any]) -> Dict[str, Any]:
    """Записывает книгу в соответствующий шаблон Ozon (до 2011 или после 2011 года)."""
    year_val = str(b.get("year", "")).strip()
    m_year = re.findall(r"\d{4}", year_val)
    if m_year:
        mode = "pre2011" if int(m_year[0]) <= 2011 else "post2011"
    else:
        raw_mode = str(b.get("template_mode") or "").strip().lower()
        mode = "post2011" if raw_mode in ("post2011", "post") else "pre2011"
    b["template_mode"] = mode

    target_file = get_target_excel_file(mode)

    with zipfile.ZipFile(target_file, "r") as z:
        files = {name: z.read(name) for name in z.namelist()}

    sst_raw = files["xl/sharedStrings.xml"].decode("utf-8")
    sheet1_raw = files["xl/worksheets/sheet1.xml"].decode("utf-8")

    sst_root = ET.fromstring(sst_raw)
    ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    existing_strings = [
        "".join(t.text for t in si.findall(".//ns:t", ns) if t.text)
        for si in sst_root.findall("ns:si", ns)
    ]

    orig_unique = int(sst_root.attrib["uniqueCount"])
    orig_total = int(sst_root.attrib["count"])
    new_strings = []

    def get_idx(s):
        s_str = str(s).strip()
        if s_str in existing_strings:
            return existing_strings.index(s_str)
        if s_str in new_strings:
            return len(existing_strings) + new_strings.index(s_str)
        new_strings.append(s_str)
        return len(existing_strings) + len(new_strings) - 1

    current_books = get_current_books(mode)
    next_row = (current_books[-1]["row"] + 1) if current_books else 5
    item_num = len(current_books) + 1

    ref_row_match = re.search(r'<row r="[56]"[^>]*>(.*?)</row>', sheet1_raw)
    styles = {}
    if ref_row_match:
        for c in re.finditer(r'<c r="([A-Z]+)\d+"[^>]*s="(\d+)"', ref_row_match.group(1)):
            s_val = c.group(2)
            if s_val in ["13", "14", "15", "16", "17"]:
                s_val = "4"
            styles[c.group(1)] = s_val

    warning_prefix = "ВНИМАНИЕ! КНИГА НЕ НОВАЯ. Имеются определённые нюансы (повреждения) см. дополнительные фото."
    annotation = b.get("annotation", "").strip()

    # Очищаем любые старые приписки о сохранности и дефектах в конце аннотации
    for marker in ["\n\nСохранность / Дефекты:", "\n\nСохранность:", "\n\nДефекты:", "Сохранность / Дефекты:", "Сохранность:"]:
        if marker in annotation:
            annotation = annotation.split(marker)[0].strip()

    # Правило: плашка-предупреждение вставляется ТОЛЬКО если есть фото мантры / дефектов (слот 5)
    slots_photos = b.get("slots_photos") or {}
    mantra_photos = slots_photos.get("mantra_defects") or []
    has_mantra_defects = bool(mantra_photos) or bool(b.get("has_mantra_defects"))

    # Очищаем warning_prefix, если он уже присутствовал в тексте
    if warning_prefix in annotation:
        annotation = annotation.replace(warning_prefix, "").strip()

    # Добавляем предупреждение строго при наличии фото нюансов/дефектов (слот 5)
    if has_mantra_defects and annotation:
        annotation = (warning_prefix + "\n\n" + annotation).strip()

    # Размеры и вес книги (нетто)
    def _parse_int_dim(keys: list, default: int) -> int:
        for k in keys:
            v = b.get(k)
            if v is not None and str(v).strip() != "":
                try:
                    iv = int(v)
                    if iv > 0:
                        return iv
                except Exception:
                    pass
        return default

    width = _parse_int_dim(["width", "width_mm"], 130)
    length = _parse_int_dim(["length", "length_mm"], 205)
    height = _parse_int_dim(["height", "height_mm"], 15)
    weight = _parse_int_dim(["weight", "weight_g"], 250)

    # Габариты упаковки (ШхДхВ в мм, вес в граммах) — обязательные поля Ozon
    is_pkg_adder = b.get("auto_package_adder") is not False
    width_pkg = _parse_int_dim(["width_package"], (width + 10) if is_pkg_adder else width)
    length_pkg = _parse_int_dim(["length_package"], (length + 10) if is_pkg_adder else length)
    height_pkg = _parse_int_dim(["height_package"], (height + 10) if is_pkg_adder else height)
    weight_pkg = _parse_int_dim(["weight_package"], (weight + 30) if is_pkg_adder else weight)

    raw_dims = b.get("dimensions")
    if isinstance(raw_dims, str) and "[object" not in raw_dims and any(sep in raw_dims for sep in ("х", "x", "X", "Х", "*", "×", "/")):
        dimensions_str = raw_dims.strip()
    else:
        dimensions_str = f"{width_pkg}х{length_pkg}х{height_pkg}"

    year_val = b.get("year", "")
    try:
        y_int = int(year_val)
        default_country = "СССР" if y_int < 1992 else "Россия"
    except Exception:
        default_country = "Россия"
    country = b.get("country") or default_country

    raw_age = b.get("age_limit")
    age_lim = str(raw_age).strip() if raw_age is not None else ""
    if age_lim not in ("0+", "6+", "12+", "16+", "18+"):
        age_lim = ""
    is_18_plus = "Да" if age_lim == "18+" else ""
    genre = normalize_genre(b.get("genre", "Проза"), str(b.get("title") or ""), str(b.get("annotation") or ""))
    publisher = clean_publisher_name(b.get("publisher", ""))
    author = normalize_author_name(b.get("author", ""))
    author_cover = normalize_author_name(b.get("author_cover", "")) or author

    brand_raw = str(b.get("brand") or "").strip()
    if not brand_raw or brand_raw.lower() in ("нет бренда", "нет", "не указан", "без бренда"):
        try:
            from services.db_service import get_catalog_references, _match_brand_from_publisher
            refs = get_catalog_references()
            brand = _match_brand_from_publisher(publisher, refs.get("brands", []))
        except Exception:
            brand = "Нет бренда"
    else:
        try:
            from services.db_service import get_catalog_references, _match_brand_from_publisher
            refs = get_catalog_references()
            matched = _match_brand_from_publisher(brand_raw, refs.get("brands", []))
            brand = matched if matched != "Нет бренда" else _match_brand_from_publisher(publisher, refs.get("brands", []))
        except Exception:
            brand = brand_raw

    article = str(b.get("article") or "").strip() or f"DP-B-{item_num:05d}"
    raw_barcode = str(b.get("barcode") or "").strip()
    if not raw_barcode or "озон" in raw_barcode.lower() or not (raw_barcode.isdigit() and len(raw_barcode) in (12, 13)):
        barcode = generate_ean13_from_article(article)
    else:
        barcode = raw_barcode

    main_photo_url = str(b.get("main_photo_url") or "").strip()
    add_photo_urls = str(b.get("add_photo_urls") or "").strip()

    # Если прямые ссылки на фото не переданы, пробуем найти их в books_vault/{article}*
    if not main_photo_url:
        tunnel_url = tunnel_service.get_tunnel_url()
        if tunnel_url and os.path.exists(VAULT_DIR):
            for d in os.listdir(VAULT_DIR):
                if d == article or d.startswith(f"{article}_"):
                    b_dir = os.path.join(VAULT_DIR, d)
                    if os.path.isdir(b_dir):
                        all_f = sorted(os.listdir(b_dir))
                        photo_files = [
                            f for f in all_f
                            if f.lower().endswith((".jpg", ".jpeg", ".png"))
                            and not f.startswith(".")
                            and not f.startswith(("03_info_page", "info_page"))
                        ]
                        main_cands = [f for f in photo_files if f.startswith("01_") or f == f"{article}.jpg"]
                        if main_cands:
                            main_photo_url = f"{tunnel_url}/vault/{article}/{main_cands[0]}"
                            add_f = [
                                f for f in photo_files
                                if f != main_cands[0]
                                and not f.startswith(f"{article}")
                                and not f.startswith(("03_info_page", "info_page"))
                            ]
                            card_f = [f for f in add_f if f.startswith("99_card")]
                            add_f_no_card = [f for f in add_f if not f.startswith("99_card")]
                            if card_f:
                                add_f = add_f_no_card[:13] + [card_f[0]]
                            else:
                                add_f = add_f_no_card[:14]
                            if add_f:
                                add_photo_urls = " ".join([f"{tunnel_url}/vault/{article}/{f}" for f in add_f])
                    break

    if mode == "pre2011":
        # ШАБЛОН ДО 2011 ГОДА (81 колонка A..CC)
        isbn_val = b.get("isbn", "").strip()

        col_map = {
            "A": ("num", item_num),
            "B": ("str", article),
            "C": ("str", b.get("title", "")),
            "D": ("num", b.get("price")) if b.get("price") else ("empty", ""),
            "E": ("num", b.get("old_price")) if b.get("old_price") else ("empty", ""),
            "F": ("str", "Не облагается"),
            "H": ("str", "Нет"),
            "K": ("str", barcode),
            "L": ("str", "4901990000 - Прочие книги, брошюры, листовки, аналогичные печатные издания, сброшюрованные"),
            "M": ("num", weight_pkg),
            "N": ("num", width_pkg),
            "O": ("num", height_pkg),
            "P": ("num", length_pkg),
            "Q": ("str", main_photo_url) if main_photo_url else ("empty", ""),
            "R": ("str", add_photo_urls) if add_photo_urls else ("empty", ""),
            "S": ("str", article),
            "T": ("str", author_cover),
            "U": ("str", author),
            "V": ("str", b.get("cover_type", "Твердый переплет")),
            "W": ("str", "Second-hand книга"),
            "X": ("str", "Печатная книга"),
            "Y": ("str", brand),
            "Z": ("str", genre),
            "AB": ("empty", ""),
            "AD": ("empty", ""),
            "AE": ("str", annotation),
            "AG": ("str", b.get("illustrator", "")),
            "AH": ("str", b.get("translator", "")),
            "AI": ("str", publisher),
            "AJ": ("str", b.get("series", "")),
            "AK": ("num", year_val) if str(year_val).isdigit() else ("empty", ""),
            "AL": ("str", b.get("paper_type", "")),
            "AM": ("str", "Русский"),
            "AN": ("num", b.get("pages")) if str(b.get("pages", "")).isdigit() else ("empty", ""),
            "AP": ("empty", ""),
            "AQ": ("empty", ""),
            "AR": ("str", isbn_val),
            "AS": ("str", normalize_condition(b.get("condition"), has_mantra_defects)),
            "AT": ("str", age_lim),
            "AU": ("str", is_18_plus),
            "BZ": ("str", country),
            "CC": ("empty", ""),
        }

        orig_title = str(b.get("original_title") or "").strip()
        if orig_title:
            col_map["BY"] = ("str", orig_title)

        # Поджанры Ozon для шаблона до 2011 года
        if genre == "Проза":
            col_map["BN"] = ("str", "Классическая проза")
        elif genre == "Фантастика":
            col_map["BQ"] = ("str", "Классическая фантастика")
        elif genre == "Детектив":
            col_map["BO"] = ("str", "Классический детектив")
        elif genre == "Поэзия":
            col_map["BT"] = ("str", "Классическая поэзия")
        elif genre == "История":
            col_map["BB"] = ("str", "История России до XIX века")
        elif genre == "Научная и научно-популярная литература":
            col_map["AX"] = ("str", "Естественные науки")
        elif genre == "Эпос и фольклор":
            col_map["BS"] = ("str", "Сказки")

        col_order = [
            "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O",
            "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA", "AB", "AC",
            "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN", "AO",
            "AP", "AQ", "AR", "AS", "AT", "AU", "AV", "AW", "AX", "AY", "AZ", "BA",
            "BB", "BC", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BK", "BL", "BM",
            "BN", "BO", "BP", "BQ", "BR", "BS", "BT", "BU", "BV", "BW", "BX", "BY",
            "BZ", "CA", "CB", "CC"
        ]
        spans_str = "1:81"

    else:
        # ШАБЛОН ПОСЛЕ 2011 ГОДА (86 колонок A..CH)
        isbn_val = b.get("isbn") or "978-5-0000-0000-0"

        col_map = {
            "A": ("num", item_num),
            "B": ("str", article),
            "C": ("str", b.get("title", "")),
            "D": ("num", b.get("price")) if b.get("price") else ("empty", ""),
            "E": ("num", b.get("old_price")) if b.get("old_price") else ("empty", ""),
            "F": ("str", "Не облагается"),
            "H": ("str", "Нет"),
            "J": ("str", barcode),
            "K": ("str", "4901990000 - Прочие книги, брошюры, листовки, аналогичные печатные издания, сброшюрованные"),
            "L": ("num", weight_pkg),
            "M": ("num", width_pkg),
            "N": ("num", height_pkg),
            "O": ("num", length_pkg),
            "P": ("str", main_photo_url) if main_photo_url else ("empty", ""),
            "Q": ("str", add_photo_urls) if add_photo_urls else ("empty", ""),
            "R": ("str", article),
            "S": ("str", author_cover),
            "T": ("str", author),
            "U": ("str", b.get("cover_type", "Твердый переплет")),
            "V": ("str", "Second-hand книга"),
            "W": ("str", "Печатная книга"),
            "X": ("str", brand),
            "Y": ("str", isbn_val),
            "Z": ("str", genre),
            "AB": ("empty", ""),
            "AD": ("empty", ""),
            "AE": ("str", annotation),
            "AG": ("str", b.get("illustrator", "")),
            "AH": ("str", b.get("translator", "")),
            "AI": ("str", b.get("series", "")),
            "AJ": ("num", year_val) if str(year_val).isdigit() else ("empty", ""),
            "AK": ("str", b.get("paper_type", "")),
            "AL": ("str", "Русский"),
            "AM": ("num", b.get("pages")) if str(b.get("pages", "")).isdigit() else ("empty", ""),
            "AO": ("empty", ""),
            "AP": ("empty", ""),
            "AQ": ("str", normalize_condition(b.get("condition"), has_mantra_defects)),
            "AR": ("str", age_lim),
            "AT": ("str", is_18_plus),
            "CE": ("str", country),
        }

        orig_title = str(b.get("original_title") or "").strip()
        if orig_title:
            col_map["CD"] = ("str", orig_title)

        # Поджанры Ozon по направлению
        if genre == "Проза":
            col_map["BM"] = ("str", "Классическая проза")
        elif genre == "Фантастика":
            col_map["BP"] = ("str", "Классическая фантастика")
        elif genre == "Детектив":
            col_map["BN"] = ("str", "Классический детектив")
        elif genre == "Поэзия":
            col_map["BS"] = ("str", "Классическая поэзия")
        elif genre == "История":
            col_map["BA"] = ("str", "История России до XIX века")
        elif genre == "Научная и научно-популярная литература":
            col_map["AW"] = ("str", "Естественные науки")
        elif genre == "Эпос и фольклор":
            col_map["BR"] = ("str", "Сказки")

        col_order = [
            "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O",
            "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA", "AB", "AC",
            "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN", "AO",
            "AP", "AQ", "AR", "AS", "AT", "AU", "AV", "AW", "AX", "AY", "AZ", "BA",
            "BB", "BC", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BK", "BL", "BM",
            "BN", "BO", "BP", "BQ", "BR", "BS", "BT", "BU", "BV", "BW", "BX", "BY",
            "BZ", "CA", "CB", "CC", "CD", "CE", "CF", "CG", "CH"
        ]
        spans_str = "1:86"

    new_cells = []
    for col in col_order:
        col_ref = f"{col}{next_row}"
        default_style = "5" if (mode == "pre2011" and col in ("D", "E")) else ("7" if (mode == "pre2011" and col == "J") else "4")
        style = styles.get(col, default_style)
        if style in ["13", "14", "15", "16", "17"]:
            style = "4"
        if col in col_map:
            t_type, val = col_map[col]
            val_str = str(val).strip()
            if t_type == "num" and val_str:
                new_cells.append(f'<c r="{col_ref}" s="{style}"><v>{val_str}</v></c>')
            elif t_type == "str" and val_str:
                idx = get_idx(val_str)
                new_cells.append(f'<c r="{col_ref}" s="{style}" t="s"><v>{idx}</v></c>')
            else:
                new_cells.append(f'<c r="{col_ref}" s="{style}"/>')
        else:
            new_cells.append(f'<c r="{col_ref}" s="{style}"/>')

    new_row_xml = (
        f'<row r="{next_row}" spans="{spans_str}" ht="20" customHeight="1" x14ac:dyDescent="0.2">'
        + "".join(new_cells)
        + "</row>"
    )

    if f'<row r="{next_row}"' in sheet1_raw:
        new_sheet1 = re.sub(rf'<row r="{next_row}"[^>]*>.*?</row>', new_row_xml, sheet1_raw)
    else:
        new_sheet1 = sheet1_raw.replace("</sheetData>", new_row_xml + "</sheetData>")

    def format_sst_si(s):
        esc = saxutils.escape(s)
        if " " in s or "\n" in s or "\t" in s:
            return f'<si><t xml:space="preserve">{esc}</t></si>'
        return f'<si><t>{esc}</t></si>'

    new_sst_items = "".join(format_sst_si(s) for s in new_strings)
    new_sst = sst_raw.replace("</sst>", f"{new_sst_items}</sst>")
    new_count = orig_total + len(new_strings)
    new_unique = orig_unique + len(new_strings)
    new_sst = re.sub(r'count="\d+"', f'count="{new_count}"', new_sst, count=1)
    new_sst = re.sub(r'uniqueCount="\d+"', f'uniqueCount="{new_unique}"', new_sst, count=1)

    files["xl/worksheets/sheet1.xml"] = new_sheet1.encode("utf-8")
    files["xl/sharedStrings.xml"] = new_sst.encode("utf-8")

    tmp_out = target_file + ".tmp"
    with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as z_out:
        for name, data in files.items():
            z_out.writestr(name, data)

    os.replace(tmp_out, target_file)
    folder_rel = os.path.relpath(os.path.dirname(target_file), BASE_DIR)
    return {
        "success": True,
        "row": next_row,
        "template_mode": mode,
        "article": article,
        "barcode": barcode,
        "title": b.get("title"),
        "file_name": os.path.basename(target_file),
        "folder": folder_rel
    }


@with_excel_lock
def clear_excel_table(mode: str = "pre2011") -> dict:
    """
    Очищает выбранную таблицу Excel Ozon (pre2011, post2011 или all),
    сохраняя резервную копию в ready_tables/backups/[era]/.
    Возвращает чистый шаблон Ozon со всеми формулами, шапкой и валидацией.
    """
    modes = ["pre2011", "post2011"] if mode == "all" else [mode]
    results = []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for m in modes:
        target_file = get_target_excel_file(m)
        subfolder = "1942-2010" if m == "pre2011" else "с_2011"
        backup_dir = os.path.join(READY_TABLES_DIR, "backups", subfolder)
        os.makedirs(backup_dir, exist_ok=True)

        clean_template = BACKUP_FILE_PRE2011 if m == "pre2011" else BACKUP_FILE_POST2011
        if not os.path.exists(clean_template):
            continue

        existing_books = get_current_books(m)
        cleared_count = len(existing_books)

        backup_file = None
        if os.path.exists(target_file) and os.path.getsize(target_file) > 0:
            target_base = os.path.basename(target_file)
            backup_filename = f"{ts}_{target_base}"
            backup_file = os.path.join(backup_dir, backup_filename)
            shutil.copyfile(target_file, backup_file)

        # Перезаписываем чистым шаблоном Ozon
        shutil.copyfile(clean_template, target_file)

        results.append({
            "mode": m,
            "filename": os.path.basename(target_file),
            "folder": os.path.relpath(os.path.dirname(target_file), BASE_DIR),
            "cleared_count": cleared_count,
            "backup_file": os.path.basename(backup_file) if backup_file else None
        })

    return {
        "success": True,
        "mode": mode,
        "results": results,
        "total_cleared": sum(r["cleared_count"] for r in results)
    }


@with_excel_lock
def delete_book_from_excel(article: str, mode: str = "pre2011") -> dict:
    """
    Удаляет конкретную строку книги по артикулу из таблицы Excel Ozon.
    1. Создает резервную копию таблицы в ready_tables/backups/[era]/.
    2. Извлекает текущие книги и отсекает удаляемую.
    3. Разворачивает чистый шаблон Ozon.
    4. Заново последовательно записывает оставшиеся книги с правильной сквозной нумерацией (№ 1, 2, 3...).
    """
    mode = "pre2011" if mode == "pre2011" else "post2011"
    target_file = get_target_excel_file(mode)
    clean_template = BACKUP_FILE_PRE2011 if mode == "pre2011" else BACKUP_FILE_POST2011

    if not os.path.exists(target_file):
        raise Exception(f"Файл таблицы ({mode}) не найден")

    # 1. Резервная копия перед удалением
    subfolder = "1942-2010" if mode == "pre2011" else "с_2011"
    backup_dir = os.path.join(READY_TABLES_DIR, "backups", subfolder)
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_base = os.path.basename(target_file)
    backup_file = os.path.join(backup_dir, f"{ts}_before_delete_{target_base}")
    shutil.copyfile(target_file, backup_file)

    # 2. Получаем текущие книги
    current_books = get_current_books(mode)
    target_art = str(article or "").strip().lower()

    deleted_book = None
    remaining_books = []
    for b in current_books:
        b_art = str(b.get("article") or "").strip().lower()
        if b_art == target_art and deleted_book is None:
            deleted_book = b
        else:
            remaining_books.append(b)

    if not deleted_book:
        raise Exception(f"Книга с артикулом '{article}' не найдена в таблице {mode}")

    # 3. Перезаписываем чистым шаблоном Ozon
    shutil.copyfile(clean_template, target_file)

    # 4. Заново добавляем оставшиеся книги
    for b in remaining_books:
        if "photo_main" in b and not b.get("main_photo_url"):
            b["main_photo_url"] = b["photo_main"]
        if "photos_additional" in b and not b.get("add_photo_urls"):
            b["add_photo_urls"] = b["photos_additional"]
        if "cover" in b and not b.get("cover_type"):
            b["cover_type"] = b["cover"]
        append_book_to_excel(b)

    return {
        "success": True,
        "mode": mode,
        "deleted_article": deleted_book.get("article"),
        "deleted_title": deleted_book.get("title"),
        "remaining_count": len(remaining_books),
        "backup_file": os.path.basename(backup_file)
    }


@with_excel_lock
def sync_book_to_excel(b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Синхронизирует книгу с официальной таблицей Excel Ozon:
    - Если строка с таким артикулом уже есть в Excel: обновляет её новыми данными.
    - Если строки нет (новая книга или строка была ранее удалена): добавляет строку в Excel.
    """
    year_val = str(b.get("year", "")).strip()
    m_year = re.findall(r"\d{4}", year_val)
    if m_year:
        mode = "pre2011" if int(m_year[0]) <= 2011 else "post2011"
    else:
        raw_mode = str(b.get("template_mode") or "").strip().lower()
        mode = "post2011" if raw_mode in ("post2011", "post") else "pre2011"
    b["template_mode"] = mode

    target_art = str(b.get("article") or "").strip().lower()

    # Удаляем старую строку из обоих шаблонов, если она там присутствовала (на случай изменения года книги)
    for m in ("pre2011", "post2011"):
        try:
            cur_books = get_current_books(m)
            if any(str(cb.get("article") or "").strip().lower() == target_art for cb in cur_books):
                delete_book_from_excel(b.get("article"), m)
        except Exception as del_err:
            print(f"⚠️ [ExcelService] Замена строки в Excel ({m}): {del_err}", flush=True)

    return append_book_to_excel(b)


