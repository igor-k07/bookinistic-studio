"""
vault_service.py: Управление хранилищем фотографий книг books_vault и архивами для Ozon.
"""

import base64
from datetime import datetime
import io
import os
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple
import zipfile

from config import VAULT_DIR, get_card_image_path


def save_book_vault_photos(
    article: str,
    title: str,
    slots_photos: Optional[Dict[str, Any]]
) -> Tuple[str, List[str]]:
    """Сохраняет обработанные фото книги в архив storage/books_vault/{article}_{clean_title}/"""
    clean_title = re.sub(r"[^\w\s-]", "", title or "book").strip().replace(" ", "_")[:40]
    folder_name = f"{article}_{clean_title}".strip("_")
    book_dir = os.path.join(VAULT_DIR, folder_name)
    os.makedirs(book_dir, exist_ok=True)

    if not slots_photos and not get_card_image_path():
        return folder_name, []

    saved_files = []

    def write_photo(filename, photo_obj, ozon_alt_name=None, is_ozon_photo=True):
        if not photo_obj or not photo_obj.get("data"):
            return
        raw_b64 = photo_obj["data"]
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        try:
            img_bytes = base64.b64decode(raw_b64)
            file_path = os.path.join(book_dir, filename)
            with open(file_path, "wb") as f:
                f.write(img_bytes)
            if is_ozon_photo:
                saved_files.append(filename)
                if ozon_alt_name:
                    alt_path = os.path.join(book_dir, ozon_alt_name)
                    with open(alt_path, "wb") as f:
                        f.write(img_bytes)
        except Exception as e:
            print(f"Ошибка сохранения фото {filename}: {e}")

    if slots_photos:
        # 1. Передняя обложка (главное фото для Ozon)
        if slots_photos.get("cover_front"):
            write_photo("01_cover_front.jpg", slots_photos["cover_front"], f"{article}.jpg", is_ozon_photo=True)

        # 2. Задняя обложка (первое доп. фото для Ozon)
        if slots_photos.get("cover_back"):
            write_photo("02_cover_back.jpg", slots_photos["cover_back"], f"{article}_1.jpg", is_ozon_photo=True)

        # 3. Инфо-страницы (титул, оборот) — сохраняем ТОЛЬКО локально для архива и ИИ, НЕ передаем в Ozon!
        for idx, p in enumerate(slots_photos.get("info_pages", []), 1):
            write_photo(f"03_info_page_{idx}.jpg", p, ozon_alt_name=None, is_ozon_photo=False)

        # 4. Иллюстрации (доп. фото для Ozon, нумерация с _2)
        cur_ozon_idx = 2
        for idx, p in enumerate(slots_photos.get("illustrations", []), 1):
            write_photo(f"04_illustration_{idx}.jpg", p, f"{article}_{cur_ozon_idx}.jpg", is_ozon_photo=True)
            cur_ozon_idx += 1

        # 5. Мантра и дефекты (доп. фото для Ozon)
        for idx, p in enumerate(slots_photos.get("mantra_defects", []), 1):
            write_photo(f"05_defect_{idx}.jpg", p, f"{article}_{cur_ozon_idx}.jpg", is_ozon_photo=True)
            cur_ozon_idx += 1

    # 6. Финальная инфо-карточка Ozon (card.png) — всегда в конце карточки книги
    card_path = get_card_image_path()
    if card_path and os.path.exists(card_path):
        try:
            # Сохраняем и как .png, и как .jpg (т.к. исходный файл card - это JPEG)
            for ext in (".jpg", ".png"):
                shutil.copyfile(card_path, os.path.join(book_dir, f"99_card{ext}"))
                shutil.copyfile(card_path, os.path.join(book_dir, f"{article}_card{ext}"))
            saved_files.append("99_card.jpg")
        except Exception as e:
            print(f"Ошибка копирования card в {book_dir}: {e}")

    return folder_name, saved_files


def create_photos_zip(article_req: str = "") -> Tuple[bytes, str]:
    """
    Формирует ZIP-архив с фото для Ozon (для одной книги или всех книг).
    Исключает служебные титульные страницы (info_page).
    Возвращает (zip_bytes, zip_filename).
    """
    zip_buffer = io.BytesIO()
    today_date = datetime.now().strftime("%d.%m.%Y")
    zip_filename = f"{today_date}_all_ozon_photos.zip"

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if article_req:
            zip_filename = f"{article_req}_ozon_photos.zip"
            matched_folder = None
            if os.path.exists(VAULT_DIR):
                for d in os.listdir(VAULT_DIR):
                    if d == article_req or d.startswith(f"{article_req}_"):
                        matched_folder = os.path.join(VAULT_DIR, d)
                        break
            if matched_folder and os.path.isdir(matched_folder):
                for fname in sorted(os.listdir(matched_folder)):
                    if (
                        fname.lower().endswith((".jpg", ".jpeg", ".png"))
                        and not fname.startswith(("03_info_page", "info_page"))
                    ):
                        fpath = os.path.join(matched_folder, fname)
                        zf.write(fpath, arcname=fname)
        else:
            if os.path.exists(VAULT_DIR):
                for root, _, files in os.walk(VAULT_DIR):
                    for fname in sorted(files):
                        if (
                            fname.lower().endswith((".jpg", ".jpeg", ".png"))
                            and not fname.startswith(("03_info_page", "info_page"))
                        ):
                            fpath = os.path.join(root, fname)
                            rel = os.path.relpath(fpath, VAULT_DIR)
                            zf.write(fpath, arcname=rel)

    return zip_buffer.getvalue(), zip_filename

