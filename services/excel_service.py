"""
excel_service.py: Управление таблицами Excel (OpenXML) для Ozon (pre2011 и post2011).
"""

from datetime import datetime
import os
import re
import shutil
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils
import zipfile
from typing import Any, Dict, List

from config import (
    BACKUP_FILE_POST2011,
    BACKUP_FILE_PRE2011,
    READY_TABLES_DIR,
    VAULT_DIR,
    get_target_excel_file,
)
from core.barcode import generate_ean13_from_article
import tunnel_manager


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
                            "dimensions": f"{get_val('N')}х{get_val('P')}х{get_val('O')}" if (get_val("N") and get_val("P")) else (get_val("AP") or "—"),
                            "weight": get_val("M") or get_val("AQ") or "",
                            "weight_package": get_val("M"),
                            "width_package": get_val("N"),
                            "height_package": get_val("O"),
                            "length_package": get_val("P"),
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
                            "dimensions": f"{get_val('M')}х{get_val('O')}х{get_val('N')}" if (get_val("M") and get_val("O")) else (get_val("AO") or "—"),
                            "weight": get_val("L") or get_val("AP") or "",
                            "weight_package": get_val("L"),
                            "width_package": get_val("M"),
                            "height_package": get_val("N"),
                            "length_package": get_val("O"),
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


def append_book_to_excel(b: Dict[str, Any]) -> Dict[str, Any]:
    """Записывает книгу в соответствующий шаблон Ozon (до 2011 или после 2011 года)."""
    mode = b.get("template_mode")
    if not mode:
        year_val = str(b.get("year", "")).strip()
        try:
            y_int = int(year_val)
            mode = "pre2011" if y_int <= 2011 else "post2011"
        except Exception:
            mode = "pre2011"

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
    try:
        width = int(b.get("width") or 130)
    except Exception:
        width = 130
    try:
        length = int(b.get("length") or 205)
    except Exception:
        length = 205
    try:
        height = int(b.get("height") or 25)
    except Exception:
        height = 25
    try:
        weight = int(b.get("weight") or 300)
    except Exception:
        weight = 300

    # Габариты упаковки (ШхДхВ в мм, вес в граммах) — обязательные поля Ozon
    is_pkg_adder = b.get("auto_package_adder") is not False
    try:
        width_pkg = int(b.get("width_package") or ((width + 10) if is_pkg_adder else width))
    except Exception:
        width_pkg = (width + 10) if is_pkg_adder else width
    try:
        length_pkg = int(b.get("length_package") or ((length + 10) if is_pkg_adder else length))
    except Exception:
        length_pkg = (length + 10) if is_pkg_adder else length
    try:
        height_pkg = int(b.get("height_package") or ((height + 10) if is_pkg_adder else height))
    except Exception:
        height_pkg = (height + 10) if is_pkg_adder else height
    try:
        weight_pkg = int(b.get("weight_package") or ((weight + 30) if is_pkg_adder else weight))
    except Exception:
        weight_pkg = (weight + 30) if is_pkg_adder else weight

    dimensions_str = b.get("dimensions") or f"{width_pkg}х{length_pkg}х{height_pkg}"

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
    genre = b.get("genre", "Проза")
    brand = b.get("brand") or "Нет бренда"
    publisher = b.get("publisher", "").strip()

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
        tunnel_url = tunnel_manager.get_tunnel_url()
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
                            add_f = add_f[:14]
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
            "D": ("num", b.get("price", "350")),
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
            "T": ("str", b.get("author_cover") or b.get("author", "Не указан")),
            "U": ("str", b.get("author") or "Не указан"),
            "V": ("str", b.get("cover_type", "Твердый переплет")),
            "W": ("str", "Second-hand книга"),
            "X": ("str", "Печатная книга"),
            "Y": ("str", brand),
            "Z": ("str", genre),
            "AB": ("str", b.get("target_audience", "Для взрослых")),
            "AD": ("empty", ""),
            "AE": ("str", annotation),
            "AG": ("str", b.get("illustrator", "")),
            "AH": ("str", b.get("translator", "")),
            "AI": ("str", b.get("series", "")),
            "AJ": ("str", publisher),
            "AK": ("num", year_val) if str(year_val).isdigit() else ("empty", ""),
            "AL": ("str", b.get("paper_type", "Офсетная")),
            "AM": ("str", "Русский"),
            "AN": ("num", b.get("pages")) if str(b.get("pages", "")).isdigit() else ("empty", ""),
            "AP": ("empty", ""),
            "AQ": ("empty", ""),
            "AR": ("str", isbn_val),
            "AS": ("str", b.get("condition", "Очень хорошая")),
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
            "D": ("num", b.get("price", "350")),
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
            "S": ("str", b.get("author_cover") or b.get("author", "Не указан")),
            "T": ("str", b.get("author") or "Не указан"),
            "U": ("str", b.get("cover_type", "Твердый переплет")),
            "V": ("str", "Second-hand книга"),
            "W": ("str", "Печатная книга"),
            "X": ("str", brand),
            "Y": ("str", isbn_val),
            "Z": ("str", genre),
            "AB": ("str", b.get("target_audience", "Для взрослых")),
            "AD": ("empty", ""),
            "AE": ("str", annotation),
            "AG": ("str", b.get("illustrator", "")),
            "AH": ("str", b.get("translator", "")),
            "AI": ("str", b.get("series", "")),
            "AJ": ("num", year_val) if str(year_val).isdigit() else ("empty", ""),
            "AK": ("str", b.get("paper_type", "Офсетная")),
            "AL": ("str", "Русский"),
            "AM": ("num", b.get("pages")) if str(b.get("pages", "")).isdigit() else ("empty", ""),
            "AO": ("empty", ""),
            "AP": ("empty", ""),
            "AQ": ("str", b.get("condition", "Очень хорошая")),
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
    return {
        "success": True,
        "row": next_row,
        "template_mode": mode,
        "article": article,
        "barcode": barcode,
        "title": b.get("title"),
        "file_name": os.path.basename(target_file),
        "folder": "ready_tables"
    }


def clear_excel_table(mode: str = "pre2011") -> dict:
    """
    Очищает выбранную таблицу Excel Ozon (pre2011, post2011 или all),
    сохраняя резервную копию в ready_tables/backups/.
    Возвращает чистый шаблон Ozon со всеми формулами, шапкой и валидацией.
    """
    modes = ["pre2011", "post2011"] if mode == "all" else [mode]
    results = []
    backup_dir = os.path.join(READY_TABLES_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for m in modes:
        target_file = get_target_excel_file(m)
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
            "cleared_count": cleared_count,
            "backup_file": os.path.basename(backup_file) if backup_file else None
        })

    return {
        "success": True,
        "mode": mode,
        "results": results,
        "total_cleared": sum(r["cleared_count"] for r in results)
    }


def delete_book_from_excel(article: str, mode: str = "pre2011") -> dict:
    """
    Удаляет конкретную строку книги по артикулу из таблицы Excel Ozon.
    1. Создает резервную копию таблицы в ready_tables/backups/.
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
    backup_dir = os.path.join(READY_TABLES_DIR, "backups")
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


