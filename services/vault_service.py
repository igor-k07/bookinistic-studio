"""
vault_service.py: Управление хранилищем фотографий книг books_vault и архивами для Ozon.
"""

import base64
from datetime import datetime
import io
import json
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple
import zipfile

from config import BASE_DIR, DRAFT_FILE, INBOX_DIR, SESSION_PHOTOS_DIR, VAULT_DIR, get_card_image_path


def resolve_photo_bytes(photo_obj_or_data: Any) -> Optional[bytes]:
    """Универсально извлекает байты изображения из объекта photo (будь то локальный путь, URL или base64)."""
    if not photo_obj_or_data:
        return None

    val = photo_obj_or_data
    if isinstance(photo_obj_or_data, dict):
        val = photo_obj_or_data.get("data") or photo_obj_or_data.get("preview") or photo_obj_or_data.get("url") or ""

    if not isinstance(val, str) or not val.strip():
        return None

    val = val.strip()

    # 1. Проверяем локальный путь / URL
    if val.startswith("/") or val.startswith("storage/"):
        clean_rel = val.lstrip("/")
        candidates = [
            os.path.join(BASE_DIR, clean_rel),
            os.path.join(BASE_DIR, "storage", clean_rel),
            os.path.join(SESSION_PHOTOS_DIR, os.path.basename(clean_rel)),
            os.path.join(INBOX_DIR, os.path.basename(clean_rel)),
            os.path.join(VAULT_DIR, clean_rel.replace("vault/", "", 1) if clean_rel.startswith("vault/") else clean_rel),
        ]
        for cand in candidates:
            if os.path.exists(cand) and os.path.isfile(cand):
                try:
                    with open(cand, "rb") as f_in:
                        return f_in.read()
                except Exception:
                    pass

    # 2. Base64
    raw_b64 = val.split(",", 1)[1] if "," in val else val
    try:
        return base64.b64decode(raw_b64)
    except Exception:
        return None


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
        if not photo_obj:
            return
        img_bytes = resolve_photo_bytes(photo_obj)
        if not img_bytes:
            return
        try:
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
        # 1. Обложка (главное фото для Ozon)
        if slots_photos.get("cover_front"):
            write_photo("01_cover_front.jpg", slots_photos["cover_front"], f"{article}.jpg", is_ozon_photo=True)

        cur_ozon_idx = 1

        # 2. Фото дефектов при наличии (первые доп. фото для Ozon)
        for idx, p in enumerate(slots_photos.get("mantra_defects", []), 1):
            write_photo(f"02_defect_{idx}.jpg", p, f"{article}_{cur_ozon_idx}.jpg", is_ozon_photo=True)
            cur_ozon_idx += 1

        # 3. Фото иллюстраций
        for idx, p in enumerate(slots_photos.get("illustrations", []), 1):
            write_photo(f"03_illustration_{idx}.jpg", p, f"{article}_{cur_ozon_idx}.jpg", is_ozon_photo=True)
            cur_ozon_idx += 1

        # 4. Фото задней части книги
        if slots_photos.get("cover_back"):
            write_photo("04_cover_back.jpg", slots_photos["cover_back"], f"{article}_{cur_ozon_idx}.jpg", is_ozon_photo=True)
            cur_ozon_idx += 1

        # Инфо-страницы (титул, оборот) — сохраняем ТОЛЬКО локально для архива и ИИ, НЕ передаем в Ozon!
        for idx, p in enumerate(slots_photos.get("info_pages", []), 1):
            write_photo(f"info_page_{idx}.jpg", p, ozon_alt_name=None, is_ozon_photo=False)

    # 5. Финальное шаблонное фото с предупреждением (card.png) — всегда в самом конце
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


def _persist_b64_to_disk(photo_id: str, suffix: str, val: Any) -> Optional[str]:
    """Сохраняет base64 изображение на диск в SESSION_PHOTOS_DIR и возвращает путь URL."""
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    if not val:
        return None
    if val.startswith("/") or val.startswith("storage/"):
        return val

    raw_b64 = val.split(",", 1)[1] if "," in val else val
    try:
        data_bytes = base64.b64decode(raw_b64)
        if len(data_bytes) < 10:
            return None
    except Exception:
        return None

    clean_id = re.sub(r"[^\w-]", "_", photo_id)
    filename = f"{clean_id}_{suffix}.jpg"
    os.makedirs(SESSION_PHOTOS_DIR, exist_ok=True)
    full_path = os.path.join(SESSION_PHOTOS_DIR, filename)
    with open(full_path, "wb") as f_out:
        f_out.write(data_bytes)
    return f"/session_photos/{filename}"


def save_session_draft_file(draft_data: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    Оптимизирует черновик сессии:
    1. Извлекает base64 изображения из photoPool и сохраняет на диск в storage/session_photos/
    2. Очищает избыточные копии полей (data, history)
    3. Приводит слоты книг в booksSession к компактным ссылкам по ID
    4. Записывает компактный JSON черновика в DRAFT_FILE (< 100 KB)
    5. Возвращает карту обновленных URL для синхронизации в памяти клиента
    """
    os.makedirs(SESSION_PHOTOS_DIR, exist_ok=True)
    updated_urls: Dict[str, Dict[str, str]] = {}

    photo_pool = draft_data.get("photoPool")
    if not isinstance(photo_pool, list):
        photo_pool = []
        draft_data["photoPool"] = photo_pool

    books_session = draft_data.get("booksSession")
    if not isinstance(books_session, list):
        books_session = []
        draft_data["booksSession"] = books_session

    # Гарантируем, что любые фото, прикрепленные к слотам, есть в photoPool
    existing_ids = {p["id"] for p in photo_pool if isinstance(p, dict) and "id" in p}
    for book in books_session:
        if not isinstance(book, dict):
            continue
        slots = book.get("slots")
        if not isinstance(slots, dict):
            continue
        for s in ("cover_front", "cover_back"):
            item = slots.get(s)
            if isinstance(item, dict) and "id" in item and item["id"] not in existing_ids:
                photo_pool.append(item)
                existing_ids.add(item["id"])
        for s in ("info_pages", "illustrations", "mantra_defects"):
            items = slots.get(s)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "id" in item and item["id"] not in existing_ids:
                        photo_pool.append(item)
                        existing_ids.add(item["id"])

    # 1. Сохраняем фото на диск и обновляем ссылки
    for photo in photo_pool:
        if not isinstance(photo, dict):
            continue
        pid = str(photo.get("id") or f"photo_{int(time.time() * 1000)}")
        clean_id = re.sub(r"[^\w-]", "_", pid)

        # Камера / исходник
        raw_orig_val = photo.get("cameraOriginal") or photo.get("rawOriginal") or photo.get("preview")
        cam_url = _persist_b64_to_disk(clean_id, "cameraOriginal", raw_orig_val)
        if cam_url:
            photo["cameraOriginal"] = cam_url
            photo["rawOriginal"] = cam_url

        # Обрезанная база
        if photo.get("croppedBase"):
            crop_url = _persist_b64_to_disk(clean_id, "croppedBase", photo["croppedBase"])
            if crop_url:
                photo["croppedBase"] = crop_url

        # ИИ-фон
        if photo.get("aiWhiteOriginal"):
            ai_url = _persist_b64_to_disk(clean_id, "aiWhiteOriginal", photo["aiWhiteOriginal"])
            if ai_url:
                photo["aiWhiteOriginal"] = ai_url

        # Превью
        prev_val = photo.get("preview")
        if prev_val == raw_orig_val and photo.get("cameraOriginal"):
            photo["preview"] = photo["cameraOriginal"]
        else:
            prev_url = _persist_b64_to_disk(clean_id, "preview", prev_val)
            if prev_url:
                photo["preview"] = prev_url
            elif photo.get("cameraOriginal") and not photo.get("preview"):
                photo["preview"] = photo["cameraOriginal"]

        # Удаляем тяжелые дубликаты и историю
        photo.pop("data", None)
        photo.pop("history", None)

        updated_urls[pid] = {
            "preview": photo.get("preview", ""),
            "cameraOriginal": photo.get("cameraOriginal", ""),
            "rawOriginal": photo.get("rawOriginal", ""),
            "croppedBase": photo.get("croppedBase"),
            "aiWhiteOriginal": photo.get("aiWhiteOriginal"),
        }

    # 2. Де-дуплицируем слоты в booksSession до ссылок по ID
    for book in books_session:
        if not isinstance(book, dict):
            continue
        slots = book.get("slots")
        if not isinstance(slots, dict):
            continue
        for s in ("cover_front", "cover_back"):
            val = slots.get(s)
            if isinstance(val, dict) and "id" in val:
                slots[s] = {"id": val["id"]}
            elif val:
                slots[s] = None
        for s in ("info_pages", "illustrations", "mantra_defects"):
            val = slots.get(s)
            if isinstance(val, list):
                slots[s] = [{"id": item["id"]} for item in val if isinstance(item, dict) and "id" in item]

    # 3. Атомарно сохраняем ультра-компактный JSON на диск
    temp_draft = DRAFT_FILE + ".tmp"
    with open(temp_draft, "w", encoding="utf-8") as f:
        json.dump(draft_data, f, ensure_ascii=False, indent=2)
    os.replace(temp_draft, DRAFT_FILE)

    return updated_urls


def clear_session_draft_storage():
    """Удаляет файл черновика и очищает временные фотографии сессии."""
    if os.path.exists(DRAFT_FILE):
        try:
            os.remove(DRAFT_FILE)
        except Exception:
            pass
    if os.path.exists(SESSION_PHOTOS_DIR):
        try:
            for fname in os.listdir(SESSION_PHOTOS_DIR):
                if fname.startswith("."):
                    continue
                fpath = os.path.join(SESSION_PHOTOS_DIR, fname)
                if os.path.isfile(fpath) or os.path.islink(fpath):
                    os.remove(fpath)
        except Exception:
            pass


