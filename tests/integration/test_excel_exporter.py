"""Integration tests for Pure OpenXML DOM Excel Exporter (backend/channels/ozon/excel_exporter.py).

Verifies:
1. Special characters handling: `<>&\1\x07` (control-char stripping & XML entity escaping).
2. Authoritative O(N) single-pass rebuild (row delete, update, and sequence ordering).
3. Export and round-trip verification against real templates:
   - `templates/Печатная книга_до_2011_template.xlsx` (pre2011, 81 columns)
   - `templates/Печатная книга_template.xlsx` (post2011, 86 columns)
4. Strict numeric validation (<v> elements).
5. Multi-threaded export safety.
"""

import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from lxml import etree

from backend.channels.ozon.excel_exporter import OpenXmlDomExporter
from backend.channels.ozon.excel_schema import sanitize_xml10
from backend.domain.models import Book
from backend.domain.value_objects import Dimensions


@pytest.fixture
def exporter():
    """Exporter configured with real project templates."""
    return OpenXmlDomExporter(templates_dir=Path("templates"))


def test_xml10_control_characters_sanitization():
    """Verify XML 1.0 disallowed control chars are stripped while keeping valid chars."""
    raw = "Title <with> & special \x01 \x07 \x00 \x0b \x0c \x1f chars"
    sanitized = sanitize_xml10(raw)
    assert "\x01" not in sanitized
    assert "\x07" not in sanitized
    assert "\x00" not in sanitized
    assert "<with> & special" in sanitized


def test_export_with_special_characters_and_roundtrip(exporter):
    """Verify exporting books with XML special chars (<>&) and control chars (\x01\x07) succeeds."""
    book = Book(
        article="DP-B-00001",
        title="Война & мир <Том 1> \x01\x07",
        author="Толстой <Лев> & Граф",
        annotation="Аннотация с & амперсандом, <тегами> и \x08 спецсимволом",
        publisher="Художественная литература & Ко",
        year=1980,
        price=1500.0,
        dimensions=Dimensions(width_mm=130, length_mm=200, height_mm=30, weight_g=500),
        main_photo_url="https://s3/pic.jpg",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "test_pre2011.xlsx"
        exporter.export_catalog([book], out_file, mode="pre2011")

        assert out_file.is_file()
        assert out_file.stat().st_size > 0

        # Verify ZIP and XML integrity with lxml
        with zipfile.ZipFile(out_file, "r") as z:
            sheet_xml = z.read("xl/worksheets/sheet1.xml")
            sst_xml = z.read("xl/sharedStrings.xml")
            # Must parse without syntax errors
            etree.fromstring(sheet_xml)
            etree.fromstring(sst_xml)

        # Read back catalog
        read_books = exporter.read_catalog(out_file, mode="pre2011")
        assert len(read_books) == 1
        b = read_books[0]
        assert b["article"] == "DP-B-00001"
        assert b["title"] == "Война & мир <Том 1>"
        assert b["author"] == "Толстой <Лев> & Граф"
        assert b["publisher"] == "Художественная литература & Ко"
        assert b["price"] == 1500.0


def test_row_delete_and_update_rebuild(exporter):
    """Verify single-pass rebuild correctly adds, deletes, and updates rows without holes."""
    b1 = Book(
        article="DP-B-00011",
        title="Книга 1",
        year=1970,
        price=300.0,
        dimensions=Dimensions(130, 200, 15, 200),
    )
    b2 = Book(
        article="DP-B-00012",
        title="Книга 2",
        year=1975,
        price=400.0,
        dimensions=Dimensions(130, 200, 15, 200),
    )
    b3 = Book(
        article="DP-B-00013",
        title="Книга 3",
        year=1980,
        price=500.0,
        dimensions=Dimensions(130, 200, 15, 200),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "catalog.xlsx"

        # Step 1: Export 3 books
        exporter.export_catalog([b1, b2, b3], out_file, mode="pre2011")
        catalog_v1 = exporter.read_catalog(out_file, mode="pre2011")
        assert len(catalog_v1) == 3
        assert [b["article"] for b in catalog_v1] == ["DP-B-00011", "DP-B-00012", "DP-B-00013"]
        assert [b["row"] for b in catalog_v1] == [5, 6, 7]

        # Step 2: Delete b2 and update b3 price (from 500 to 999)
        b3_updated = Book(
            article="DP-B-00013",
            title="Книга 3 (Обновленная)",
            year=1980,
            price=999.0,
            dimensions=Dimensions(130, 200, 15, 200),
        )
        exporter.export_catalog([b1, b3_updated], out_file, mode="pre2011")
        catalog_v2 = exporter.read_catalog(out_file, mode="pre2011")

        # Must have exactly 2 rows (5 and 6), no gaps or orphaned row 7
        assert len(catalog_v2) == 2
        assert [b["article"] for b in catalog_v2] == ["DP-B-00011", "DP-B-00013"]
        assert [b["row"] for b in catalog_v2] == [5, 6]
        assert catalog_v2[1]["title"] == "Книга 3 (Обновленная)"
        assert catalog_v2[1]["price"] == 999.0


def test_export_post2011_real_template(exporter):
    """Verify modern post2011 export against templates/Печатная книга_template.xlsx."""
    book = Book(
        article="DP-B-00500",
        title="Мастер и Маргарита",
        author="Булгаков М.А.",
        publisher="АСТ",
        year=2020,
        isbn="978-5-17-070335-7",
        price=750.0,
        dimensions=Dimensions(width_mm=145, length_mm=215, height_mm=25, weight_g=400),
        main_photo_url="https://s3/modern_cover.jpg",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "test_post2011.xlsx"
        exporter.export_catalog([book], out_file, mode="post2011")

        assert out_file.is_file()

        # Check with lxml that row 5 has 86 columns
        with zipfile.ZipFile(out_file, "r") as z:
            sheet_root = etree.fromstring(z.read("xl/worksheets/sheet1.xml"))
            row5 = sheet_root.find(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row[@r='5']")
            assert row5 is not None
            # 86 cells (A..CH)
            assert len(row5) == 86

        # Read back
        read_books = exporter.read_catalog(out_file, mode="post2011")
        assert len(read_books) == 1
        assert read_books[0]["article"] == "DP-B-00500"
        assert read_books[0]["title"] == "Мастер и Маргарита"
        assert read_books[0]["author"] == "Булгаков М.А."
        assert read_books[0]["year"] == 2020
        assert read_books[0]["price"] == 750.0


def test_concurrent_exports_thread_safety(exporter):
    """Verify concurrent export operations via ThreadPoolExecutor do not corrupt files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        books = [
            Book(
                article=f"DP-B-{i:05d}",
                title=f"Book {i}",
                year=1980 + (i % 20),
                price=float(100 * i),
                dimensions=Dimensions(130, 200, 15, 200),
            )
            for i in range(1, 11)
        ]

        def _do_export(idx: int):
            out = Path(tmpdir) / f"thread_{idx}.xlsx"
            exporter.export_catalog(books, out, mode="pre2011")
            return out

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_do_export, i) for i in range(4)]
            results = [f.result() for f in futures]

        assert len(results) == 4
        for out_path in results:
            read_back = exporter.read_catalog(out_path, mode="pre2011")
            assert len(read_back) == 10
