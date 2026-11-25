"""Integration tests for VaultStore: atomic storage, path stability, and streaming ZIP (Step 3.2)."""

import io
import zipfile
from pathlib import Path

from backend.infrastructure.media.vault_store import VaultStore


def test_title_rename_never_creates_duplicate_folders(tmp_path: Path) -> None:
    """Verify that changing a book title NEVER creates duplicate or orphaned folders in vault."""
    vault = VaultStore(tmp_path / "vault")
    article = "DP-B-10001"

    photo1 = ("01_cover_front.jpg", b"fake_front_jpg_data", b"fake_raw_source")
    photo2 = ("04_cover_back.jpg", b"fake_back_jpg_data", None)

    # Initial save with Title A
    meta1 = {"title": "Война и мир", "author": "Лев Толстой"}
    book_dir1 = vault.save_book_vault(article, meta1, [photo1, photo2])

    assert book_dir1 == tmp_path / "vault" / "DP-B-10001"
    assert book_dir1.is_dir()
    assert (book_dir1 / "01_cover_front.jpg").is_file()
    assert (book_dir1 / "raw_sources" / "01_cover_front.jpg").is_file()

    # User renames title to Title B and saves
    meta2 = {"title": "Война и мир. Том 1-4 (Полное собрание)", "author": "Лев Толстой"}
    book_dir2 = vault.save_book_vault(article, meta2, [photo1, photo2])

    assert book_dir2 == book_dir1
    # Verify ONLY 1 directory exists in vault
    vault_subdirs = [p for p in (tmp_path / "vault").iterdir() if p.is_dir()]
    assert len(vault_subdirs) == 1
    assert vault_subdirs[0].name == "DP-B-10001"

    manifest = vault.get_manifest(article)
    assert manifest is not None
    assert manifest["title"] == "Война и мир. Том 1-4 (Полное собрание)"


def test_ozon_zip_strictly_excludes_raw_sources_and_info_pages(tmp_path: Path) -> None:
    """Verify Ozon export ZIP excludes internal info_page_* and raw_sources/."""
    vault = VaultStore(tmp_path / "vault")
    article = "DP-B-10002"

    photos = [
        ("01_cover_front.jpg", b"front_bytes", b"raw_front_bytes"),
        ("04_cover_back.jpg", b"back_bytes", None),
        ("info_page_1.jpg", b"info_1_bytes", b"raw_info_bytes"),
        ("info_page_2.jpg", b"info_2_bytes", None),
        ("99_card.jpg", b"card_bytes", None),
    ]
    vault.save_book_vault(article, {"title": "Редкая книга"}, photos)

    # 1. Test create_ozon_zip to file
    zip_path = tmp_path / "export.zip"
    count = vault.create_ozon_zip(article, zip_path)
    assert count == 3  # cover_front, cover_back, 99_card

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "01_cover_front.jpg" in names
        assert "04_cover_back.jpg" in names
        assert "99_card.jpg" in names
        # MUST NOT contain info pages, raw sources, or manifest
        assert "info_page_1.jpg" not in names
        assert "info_page_2.jpg" not in names
        assert "manifest.json" not in names
        assert not any("raw_sources" in n for n in names)

    # 2. Test stream_ozon_zip into in-memory stream
    stream = io.BytesIO()
    stream_count = vault.stream_ozon_zip(article, stream)
    assert stream_count == 3
    stream.seek(0)

    with zipfile.ZipFile(stream, "r") as zf_stream:
        names_stream = zf_stream.namelist()
        assert "01_cover_front.jpg" in names_stream
        assert "info_page_1.jpg" not in names_stream


def test_manifest_sanitizes_base64_strings(tmp_path: Path) -> None:
    """Verify Base64 strings are stripped from manifest to maintain lightweight state."""
    vault = VaultStore(tmp_path / "vault")
    article = "DP-B-10003"

    meta_with_base64 = {
        "title": "Книга с картинкой",
        "preview_data": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD...",
        "large_blob": "A" * 6000,
        "clean_field": "Обычный текст",
    }
    vault.save_book_vault(article, meta_with_base64, [])

    manifest = vault.get_manifest(article)
    assert manifest is not None
    assert "preview_data" not in manifest
    assert "large_blob" not in manifest
    assert manifest["clean_field"] == "Обычный текст"
