"""Pure OpenXML DOM Excel Exporter for Ozon Marketplace (Zero Regex!).

Architectural Guarantees:
- Zero regex hacking on XML — 100% lxml.etree DOM manipulation.
- Strict numeric validation on <v> elements.
- Concurrency protection: fcntl.flock + threading.RLock.
- Single-pass O(N) rebuild from authoritative Book models.
- Atomic file writes (.tmp -> final .xlsx).
"""

from __future__ import annotations

import fcntl
import logging
import os
import re
import threading
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from lxml import etree

from backend.channels.ozon.excel_schema import (
    MAIN_NS,
    NS_MAIN,
    NS_XML,
    QNAME_C,
    QNAME_ROW,
    QNAME_SHEETDATA,
    QNAME_SI,
    QNAME_T,
    QNAME_V,
    SCHEMAS,
    SheetSchema,
    is_valid_numeric_string,
    sanitize_xml10,
    sanitize_xml_text,
)
from backend.domain.enums import BookEra
from backend.domain.models import Book

logger = logging.getLogger(__name__)

__all__ = [
    "OpenXmlDomExporter",
    "MAIN_NS",
    "NS_MAIN",
    "NS_XML",
    "sanitize_xml_text",
    "sanitize_xml10",
]


class OpenXmlDomExporter:
    """High-performance OpenXML DOM Excel Exporter with zero regex."""

    def __init__(self, templates_dir: Optional[Path] = None) -> None:
        self.templates_dir = templates_dir or Path("templates")
        self._thread_lock = threading.RLock()

    def get_template_path(self, mode: str) -> Path:
        schema = SCHEMAS.get(mode, SCHEMAS["pre2011"])
        tmpl = self.templates_dir / schema.template_filename
        if not tmpl.is_file():
            raise FileNotFoundError(f"Ozon template not found at {tmpl}")
        return tmpl

    def rebuild_sheet(
        self,
        books: List[Book],
        mode: str,
        output_path: Path,
        template_path: Optional[Path] = None,
    ) -> Path:
        """Single-pass O(N) rebuild of Excel catalog from authoritative books."""
        schema = SCHEMAS.get(mode, SCHEMAS["pre2011"])
        if template_path is None:
            template_path = self.get_template_path(mode)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lock_path = output_path.with_suffix(".lock")

        with self._thread_lock:
            with open(lock_path, "w") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    self._export_internal(schema, template_path, books, output_path)
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        return output_path

    def export_catalog(
        self,
        books: List[Book],
        output_dir_or_file: Path,
        mode: Optional[str] = None,
    ) -> Dict[str, Path]:
        """Export catalog to Excel, grouped by era or filtered by mode."""
        output_path = Path(output_dir_or_file)
        results: Dict[str, Path] = {}

        if mode is not None:
            target_file = (
                output_path
                if str(output_path).endswith(".xlsx")
                else output_path / f"catalog_{mode}.xlsx"
            )
            self.rebuild_sheet(books, mode, target_file)
            results[mode] = target_file
            return results

        pre_books = [
            b
            for b in books
            if b.template_mode == BookEra.PRE2011
            or (b.year and b.year <= 2010)
            or b.year is None
        ]
        post_books = [
            b
            for b in books
            if b.template_mode == BookEra.POST2011
            or (b.year and b.year >= 2011)
        ]

        out_dir = output_path.parent if str(output_path).endswith(".xlsx") else output_path

        if pre_books or not post_books:
            target_pre = out_dir / "catalog_pre2011.xlsx"
            self.rebuild_sheet(pre_books, "pre2011", target_pre)
            results["pre2011"] = target_pre

        if post_books:
            target_post = out_dir / "catalog_post2011.xlsx"
            self.rebuild_sheet(post_books, "post2011", target_post)
            results["post2011"] = target_post

        return results

    def _export_internal(
        self,
        schema: SheetSchema,
        template_path: Path,
        books: List[Book],
        output_path: Path,
    ) -> None:
        with zipfile.ZipFile(template_path, "r") as z_in:
            zip_entries = {name: z_in.read(name) for name in z_in.namelist()}

        # 1. Parse shared strings and sheetData
        sst_root = etree.fromstring(zip_entries["xl/sharedStrings.xml"])
        sheet_root = etree.fromstring(zip_entries["xl/worksheets/sheet1.xml"])

        existing_strings: List[str] = []
        for si in sst_root.findall(f"{QNAME_SI}"):
            existing_strings.append("".join(si.itertext()))

        string_to_idx: Dict[str, int] = {s: i for i, s in enumerate(existing_strings)}

        # 2. Extract column default styles from row 5 in template
        sheet_data = sheet_root.find(f"{QNAME_SHEETDATA}")
        if sheet_data is None:
            raise ValueError("Template worksheet missing sheetData element")

        col_styles: Dict[str, str] = {}
        row5 = sheet_data.find(f"{QNAME_ROW}[@r='5']")
        if row5 is not None:
            for cell in row5.findall(f"{QNAME_C}"):
                c_ref = cell.get("r", "")
                c_col = re.sub(r"\d+", "", c_ref)
                if c_col:
                    col_styles[c_col] = cell.get("s", "4")

        # 3. Clear all data rows (r >= 5) while preserving headers (r 1..4)
        for old_row in list(sheet_data.findall(f"{QNAME_ROW}")):
            r_num = int(old_row.get("r", "0"))
            if r_num >= 5:
                sheet_data.remove(old_row)

        # 4. Helper for shared strings allocation
        def _get_string_idx(val: str) -> int:
            clean_val = sanitize_xml10(val)
            if clean_val in string_to_idx:
                return string_to_idx[clean_val]
            new_idx = len(existing_strings)
            string_to_idx[clean_val] = new_idx
            existing_strings.append(clean_val)

            # Append to sst_root DOM
            si_elem = etree.SubElement(sst_root, QNAME_SI)
            t_elem = etree.SubElement(si_elem, QNAME_T)
            t_elem.text = clean_val
            if " " in clean_val or "\n" in clean_val or "\t" in clean_val:
                t_elem.set(f"{{{NS_XML}}}space", "preserve")
            return new_idx

        # 5. Populate rows for all books
        for idx, book in enumerate(books, 1):
            row_idx = 4 + idx
            col_map = schema.map_book(book, idx)

            row_elem = etree.SubElement(
                sheet_data,
                QNAME_ROW,
                attrib={
                    "r": str(row_idx),
                    "ht": "20",
                    "customHeight": "1",
                },
            )

            for col in schema.col_order:
                col_ref = f"{col}{row_idx}"
                style = col_styles.get(col, "4")
                if style in ("13", "14", "15", "16", "17"):
                    style = "4"

                cell_elem = etree.SubElement(
                    row_elem,
                    QNAME_C,
                    attrib={"r": col_ref, "s": style},
                )

                if col in col_map:
                    cell_type, raw_val = col_map[col]
                    clean_str = sanitize_xml10(
                        str(raw_val) if raw_val is not None else ""
                    ).strip()

                    if cell_type == "num" and is_valid_numeric_string(clean_str):
                        v_elem = etree.SubElement(cell_elem, QNAME_V)
                        v_elem.text = clean_str
                    elif cell_type == "str" and clean_str:
                        sst_idx = _get_string_idx(clean_str)
                        cell_elem.set("t", "s")
                        v_elem = etree.SubElement(cell_elem, QNAME_V)
                        v_elem.text = str(sst_idx)

        # 6. Update SST counts in DOM
        sst_root.set("count", str(len(existing_strings)))
        sst_root.set("uniqueCount", str(len(existing_strings)))

        # 7. Serialize XML DOM back to bytes
        zip_entries["xl/sharedStrings.xml"] = etree.tostring(
            sst_root, xml_declaration=True, encoding="utf-8"
        )
        zip_entries["xl/worksheets/sheet1.xml"] = etree.tostring(
            sheet_root, xml_declaration=True, encoding="utf-8"
        )

        # 8. Atomic file swap via .tmp
        tmp_output = output_path.with_suffix(".tmp")
        with zipfile.ZipFile(tmp_output, "w", zipfile.ZIP_DEFLATED) as z_out:
            for name, content in zip_entries.items():
                z_out.writestr(name, content)

        os.replace(tmp_output, output_path)
        logger.info(
            "Exported %d books to Excel: %s (%s)",
            len(books),
            output_path,
            schema.mode,
        )

    def read_catalog(
        self, file_path: Path, mode: str = "pre2011"
    ) -> List[Dict[str, Any]]:
        """Read books from an existing Ozon Excel file."""
        if not file_path.is_file():
            return []

        with zipfile.ZipFile(file_path, "r") as z:
            sheet_root = etree.fromstring(z.read("xl/worksheets/sheet1.xml"))
            sst_root = etree.fromstring(z.read("xl/sharedStrings.xml"))

        strings: List[str] = []
        for si in sst_root.findall(f"{QNAME_SI}"):
            strings.append("".join(si.itertext()))

        sheet_data = sheet_root.find(f"{QNAME_SHEETDATA}")
        if sheet_data is None:
            return []

        results: List[Dict[str, Any]] = []
        for row in sheet_data.findall(f"{QNAME_ROW}"):
            r_num = int(row.get("r", "0"))
            if r_num < 5:
                continue

            cell_vals: Dict[str, str] = {}
            for c in row.findall(f"{QNAME_C}"):
                c_ref = c.get("r", "")
                col = re.sub(r"\d+", "", c_ref)
                t_attr = c.get("t")
                v_el = c.find(f"{QNAME_V}")
                v_text = v_el.text if v_el is not None and v_el.text else ""

                if t_attr == "s" and v_text.isdigit():
                    idx = int(v_text)
                    val = strings[idx] if idx < len(strings) else ""
                else:
                    val = v_text
                cell_vals[col] = val

            art = cell_vals.get("B", "").strip()
            title = cell_vals.get("C", "").strip()
            if art or title:
                results.append({
                    "row": r_num,
                    "article": art,
                    "title": title,
                    "price": float(cell_vals.get("D") or 0.0),
                    "author": cell_vals.get(
                        "U" if mode == "pre2011" else "T", ""
                    ),
                    "publisher": cell_vals.get(
                        "AI" if mode == "pre2011" else "AI", ""
                    ),
                    "year": int(
                        cell_vals.get("AK" if mode == "pre2011" else "AJ") or 0
                    )
                    or None,
                    "isbn": cell_vals.get(
                        "AR" if mode == "pre2011" else "Y", ""
                    ),
                    "main_photo_url": cell_vals.get(
                        "Q" if mode == "pre2011" else "P", ""
                    ),
                })

        return results
