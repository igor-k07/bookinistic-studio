"""Declarative column schemas and mappings for Ozon Excel templates.

Defines:
- COLS_PRE2011 (81 columns, A..CC, Category 200001485)
- COLS_POST2011 (86 columns, A..CH, Category 200001483)
- SheetSchema declarative book-to-column mapper
- XML OpenXML namespaces and QNames
- XML 1.0 control char sanitization
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend.domain.models import Book

# OpenXML Namespaces
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_MAIN = MAIN_NS
NS_XML = "http://www.w3.org/XML/1998/namespace"

# XML Qualified Element Names
QNAME_ROW = f"{{{MAIN_NS}}}row"
QNAME_C = f"{{{MAIN_NS}}}c"
QNAME_V = f"{{{MAIN_NS}}}v"
QNAME_T = f"{{{MAIN_NS}}}t"
QNAME_SI = f"{{{MAIN_NS}}}si"
QNAME_SHEETDATA = f"{{{MAIN_NS}}}sheetData"

# XML 1.0 illegal control characters: \x00-\x08, \x0b-\x0c, \x0e-\x1f, \ufffe-\uffff
_XML10_INVALID_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def sanitize_xml_text(text: Optional[str]) -> str:
    """Strip XML 1.0 illegal control characters without corrupting text."""
    if not text:
        return ""
    return _XML10_INVALID_CHARS.sub("", str(text))


# Alias for backward compatibility and internal consistency
sanitize_xml10 = sanitize_xml_text


def is_valid_numeric_string(val: str) -> bool:
    """Validate that string represents a valid numeric value for OpenXML <v>."""
    if not val:
        return False
    val_strip = val.strip()
    if not val_strip:
        return False
    try:
        float(val_strip)
        return True
    except ValueError:
        return False


# Columns list A..CC (81 columns for pre2011)
COLS_PRE2011: List[str] = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O",
    "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA", "AB", "AC",
    "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN", "AO",
    "AP", "AQ", "AR", "AS", "AT", "AU", "AV", "AW", "AX", "AY", "AZ", "BA",
    "BB", "BC", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BK", "BL", "BM",
    "BN", "BO", "BP", "BQ", "BR", "BS", "BT", "BU", "BV", "BW", "BX", "BY",
    "BZ", "CA", "CB", "CC"
]

# Columns list A..CH (86 columns for post2011)
COLS_POST2011: List[str] = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O",
    "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA", "AB", "AC",
    "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN", "AO",
    "AP", "AQ", "AR", "AS", "AT", "AU", "AV", "AW", "AX", "AY", "AZ", "BA",
    "BB", "BC", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BK", "BL", "BM",
    "BN", "BO", "BP", "BQ", "BR", "BS", "BT", "BU", "BV", "BW", "BX", "BY",
    "BZ", "CA", "CB", "CC", "CD", "CE", "CF", "CG", "CH"
]


@dataclass(frozen=True)
class SheetSchema:
    """Declarative specification for Ozon template schema."""

    mode: str
    template_filename: str
    total_columns: int
    col_order: List[str]

    def map_book(self, book: Book, item_num: int) -> Dict[str, Tuple[str, Any]]:
        """Map Book entity to dictionary of {col_letter: (type, value)}."""
        dims = book.dimensions
        w_pkg = dims.width_mm + 10 if dims else 140
        l_pkg = dims.length_mm + 15 if dims else 215
        h_pkg = dims.height_mm + 10 if dims else 25
        wt_pkg = dims.weight_g + 50 if dims else 330

        price_val = str(int(book.price)) if book.price and book.price > 0 else ""
        old_price_val = (
            str(int(book.old_price))
            if book.old_price and book.old_price > 0
            else ""
        )
        year_str = str(book.year) if book.year else ""
        pages_str = str(book.pages) if book.pages and book.pages > 0 else ""
        country = "СССР" if (book.year and book.year <= 1991) else "Россия"
        add_photos_str = (
            " ".join(book.add_photo_urls[:14]) if book.add_photo_urls else ""
        )

        col_map: Dict[str, Tuple[str, Any]] = {}
        if self.mode == "pre2011":
            col_map = {
                "A": ("num", item_num),
                "B": ("str", book.article),
                "C": ("str", book.title),
                "D": ("num", price_val) if price_val else ("empty", ""),
                "E": ("num", old_price_val) if old_price_val else ("empty", ""),
                "F": ("str", "Не облагается"),
                "H": ("str", "Нет"),
                "K": ("str", book.barcode or ""),
                "L": (
                    "str",
                    "4901990000 - Прочие книги, брошюры, листовки, аналогичные печатные издания, сброшюрованные",
                ),
                "M": ("num", wt_pkg),
                "N": ("num", w_pkg),
                "O": ("num", h_pkg),
                "P": ("num", l_pkg),
                "Q": ("str", book.main_photo_url or ""),
                "R": ("str", add_photos_str),
                "S": ("str", book.article),
                "T": ("str", book.author_cover or book.author),
                "U": ("str", book.author),
                "V": ("str", book.cover_type or "Твердый переплет"),
                "W": ("str", "Second-hand книга"),
                "X": ("str", "Печатная книга"),
                "Y": ("str", book.brand or book.publisher or ""),
                "Z": ("str", book.genre or "Проза"),
                "AE": ("str", book.annotation or ""),
                "AG": ("str", book.illustrator or ""),
                "AH": ("str", book.translator or ""),
                "AI": ("str", book.publisher or ""),
                "AJ": ("str", book.series or ""),
                "AK": ("num", year_str) if year_str else ("empty", ""),
                "AL": ("str", book.paper_type or ""),
                "AM": ("str", "Русский"),
                "AN": ("num", pages_str) if pages_str else ("empty", ""),
                "AR": ("str", book.isbn or ""),
                "AS": (
                    "str",
                    book.condition.value
                    if hasattr(book.condition, "value")
                    else str(book.condition),
                ),
                "AT": ("str", book.age_limit or ""),
                "BZ": ("str", country),
            }
            if book.original_title:
                col_map["BY"] = ("str", book.original_title)
        else:
            col_map = {
                "A": ("num", item_num),
                "B": ("str", book.article),
                "C": ("str", book.title),
                "D": ("num", price_val) if price_val else ("empty", ""),
                "E": ("num", old_price_val) if old_price_val else ("empty", ""),
                "F": ("str", "Не облагается"),
                "H": ("str", "Нет"),
                "J": ("str", book.barcode or ""),
                "K": (
                    "str",
                    "4901990000 - Прочие книги, брошюры, листовки, аналогичные печатные издания, сброшюрованные",
                ),
                "L": ("num", wt_pkg),
                "M": ("num", w_pkg),
                "N": ("num", h_pkg),
                "O": ("num", l_pkg),
                "P": ("str", book.main_photo_url or ""),
                "Q": ("str", add_photos_str),
                "R": ("str", book.article),
                "S": ("str", book.author_cover or book.author),
                "T": ("str", book.author),
                "U": ("str", book.cover_type or "Твердый переплет"),
                "V": ("str", "Second-hand книга"),
                "W": ("str", "Печатная книга"),
                "X": ("str", book.brand or book.publisher or ""),
                "Y": ("str", book.isbn or ""),
                "Z": ("str", book.genre or "Проза"),
                "AE": ("str", book.annotation or ""),
                "AG": ("str", book.illustrator or ""),
                "AH": ("str", book.translator or ""),
                "AI": ("str", book.series or ""),
                "AJ": ("num", year_str) if year_str else ("empty", ""),
                "AK": ("str", book.paper_type or ""),
                "AL": ("str", "Русский"),
                "AM": ("num", pages_str) if pages_str else ("empty", ""),
                "AQ": (
                    "str",
                    book.condition.value
                    if hasattr(book.condition, "value")
                    else str(book.condition),
                ),
                "AR": ("str", book.age_limit or ""),
                "CE": ("str", country),
            }
            if book.original_title:
                col_map["CD"] = ("str", book.original_title)

        return col_map


SCHEMAS: Dict[str, SheetSchema] = {
    "pre2011": SheetSchema(
        mode="pre2011",
        template_filename="Печатная книга_до_2011_template.xlsx",
        total_columns=81,
        col_order=COLS_PRE2011,
    ),
    "post2011": SheetSchema(
        mode="post2011",
        template_filename="Печатная книга_template.xlsx",
        total_columns=86,
        col_order=COLS_POST2011,
    ),
}


def read_sheet_articles(xlsx_path: Any, start_row: int = 5) -> List[str]:
    """Read article codes from column B (rows >= start_row) using pure lxml DOM."""
    import zipfile
    from pathlib import Path

    from lxml import etree

    path = Path(xlsx_path)
    if not path.is_file():
        return []

    articles: List[str] = []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            shared: List[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                ss_root = etree.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in ss_root.findall(QNAME_SI):
                    parts = [t.text or "" for t in si.iter(QNAME_T)]
                    shared.append("".join(parts))

            if "xl/worksheets/sheet1.xml" not in zf.namelist():
                return []

            sheet_root = etree.fromstring(zf.read("xl/worksheets/sheet1.xml"))
            sheet_data = sheet_root.find(QNAME_SHEETDATA)
            if sheet_data is None:
                return []

            for row_el in sheet_data.findall(QNAME_ROW):
                r_num = int(row_el.get("r", "0") or 0)
                if r_num < start_row:
                    continue
                for c_el in row_el.findall(QNAME_C):
                    ref = c_el.get("r", "")
                    if not (ref.startswith("B") and ref[1:].isdigit()):
                        continue
                    c_type = c_el.get("t", "")
                    val = ""
                    if c_type == "s":
                        v_el = c_el.find(QNAME_V)
                        if v_el is not None and v_el.text and v_el.text.isdigit():
                            idx = int(v_el.text)
                            if 0 <= idx < len(shared):
                                val = shared[idx]
                    elif c_type == "inlineStr":
                        val = "".join(t.text or "" for t in c_el.iter(QNAME_T))
                    else:
                        v_el = c_el.find(QNAME_V)
                        if v_el is not None and v_el.text:
                            val = v_el.text
                    val = val.strip()
                    if val:
                        articles.append(val)
    except Exception:
        return []
    return articles
