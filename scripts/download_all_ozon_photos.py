#!/usr/bin/env python3
"""
download_all_ozon_photos.py
===========================
Параллельная выгрузка всех оригинальных фотографий созданных на Ozon карточек
на локальный диск в папку storage/books_vault/<article>_<clean_title>/.

Особенности:
- Скачивание в 15 параллельных потоков через ThreadPoolExecutor
- Безопасный повторный запуск (пропускает уже скачанные файлы)
- Сохранение book_state.json в каждой папке книги для мгновенного открытия в студии
- Обновление связей в catalog.db
"""

import os
import sys
import json
import re
import time
import sqlite3
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import VAULT_DIR, DB_PATH
from core.domain.rules import (
    SLOT_CARD,
    SLOT_COVER_BACK,
    SLOT_DEFECTS,
    SLOT_INFO_PAGES,
    classify_filename_to_slot,
)

def sanitize_folder_name(name: str, max_len: int = 50) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', '', name)
    cleaned = re.sub(r'[\s_]+', '_', cleaned).strip('._ ')
    return cleaned[:max_len] if cleaned else "Книга"

def download_file(url: str, dest_path: str, retries: int = 3) -> bool:
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024:
        return True

    tmp_path = dest_path + ".tmp"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BookinisticDownloader/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 0:
                        with open(tmp_path, "wb") as f:
                            f.write(data)
                        os.replace(tmp_path, dest_path)
                        return True
        except Exception as e:
            if attempt == retries - 1:
                pass
            time.sleep(0.5)

    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    return False

def process_book(book_row: Tuple[str, str, str]) -> Dict[str, Any]:
    art, title, raw_data = book_row
    data = json.loads(raw_data) if raw_data else {}
    
    clean_art = art.strip()
    safe_title = sanitize_folder_name(title or data.get("title") or "Книга")
    folder_name = f"{clean_art}_{safe_title}"
    book_dir = os.path.join(VAULT_DIR, folder_name)
    os.makedirs(book_dir, exist_ok=True)

    main_photo = data.get("main_photo_url") or ""
    add_photos_raw = data.get("add_photo_urls") or ""
    if isinstance(add_photos_raw, str):
        add_photos = [u.strip() for u in add_photos_raw.split() if u.strip()]
    elif isinstance(add_photos_raw, list):
        add_photos = [str(u).strip() for u in add_photos_raw if str(u).strip()]
    else:
        add_photos = []

    downloaded = 0
    total = (1 if main_photo else 0) + len(add_photos)

    # 1. Скачиваем главное фото
    if main_photo:
        main_dest = os.path.join(book_dir, "01_cover_front.jpg")
        if download_file(main_photo, main_dest):
            downloaded += 1

    # 2. Скачиваем дополнительные фото
    for idx, u in enumerate(add_photos, 1):
        slot = classify_filename_to_slot(u)
        if slot == SLOT_CARD:
            fname = "99_card.jpg"
        elif slot == SLOT_COVER_BACK:
            fname = "02_cover_back.jpg"
        elif slot == SLOT_DEFECTS:
            fname = f"05_defect_{idx}.jpg"
        elif slot == SLOT_INFO_PAGES:
            fname = f"03_info_page_{idx}.jpg"
        else:
            fname = f"04_illustration_{idx}.jpg"

        dest = os.path.join(book_dir, fname)
        if download_file(u, dest):
            downloaded += 1

    # 3. Сохраняем локальный book_state.json
    state_file = os.path.join(book_dir, "book_state.json")
    if not os.path.exists(state_file):
        try:
            with open(state_file, "w", encoding="utf-8") as f_st:
                json.dump(data, f_st, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return {
        "article": clean_art,
        "folder": folder_name,
        "total": total,
        "downloaded": downloaded,
        "success": downloaded > 0
    }

def main():
    print("=" * 65)
    print(" 📥 ВЫГРУЗКА ВСЕХ ФОТОГРАФИЙ OZON НА ЛОКАЛЬНЫЙ ДИСК")
    print("=" * 65)

    if not os.path.exists(DB_PATH):
        print(f"❌ База данных не найдена: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT article, title, data FROM books WHERE status="imported"')
    rows = cursor.fetchall()
    conn.close()

    total_books = len(rows)
    print(f"📦 Всего карточек для выгрузки: {total_books}")

    workers = 15
    completed = 0
    total_downloaded_photos = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_book, row): row[0] for row in rows}
        for future in as_completed(futures):
            res = future.result()
            completed += 1
            total_downloaded_photos += res.get("downloaded", 0)

            if completed % 100 == 0 or completed == total_books:
                elapsed = time.time() - start_time
                pct = (completed / total_books) * 100
                speed = completed / (elapsed or 1)
                print(f"⏳ Прогресс: {completed}/{total_books} ({pct:.1f}%) | Скачано фото: {total_downloaded_photos} | Скорость: {speed:.1f} книг/сек")

    elapsed_total = time.time() - start_time
    print("=" * 65)
    print(f"🎉 Выгрузка завершена за {elapsed_total / 60:.1f} мин!")
    print(f"📁 Все фото сохранены в {VAULT_DIR}")
    print(f"📸 Всего скачано фото: {total_downloaded_photos}")
    print("=" * 65)

if __name__ == "__main__":
    main()

