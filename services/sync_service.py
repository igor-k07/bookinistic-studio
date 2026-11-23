"""
sync_service.py: Умная инкрементальная синхронизация карточек Ozon, Yandex Cloud S3 и catalog.db.

Архитектура:
1. Инкрементальная выгрузка фото в S3:
   - Фото стримятся из CDN Ozon (ir.ozone.ru) напрямую в Yandex S3 в оперативной памяти (без записи на диск).
   - Если фото книги уже на S3 — книга пропускается мгновенно (smart skip).
2. Обновление SQLite catalog.db:
   - В catalog.db записываются постоянные публичные ссылки Yandex S3.
3. Синхронизация базы в облако:
   - Резервная копия catalog.db загружается в Yandex S3 (backups/db/catalog_latest.db).
4. Инкрементальный опрос Ozon:
   - Подгружает только новые карточки и фото, которых еще нет в БД и на S3.
"""

import json
import os
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import DB_PATH, get_db_path
from core.domain.rules import (
    SLOT_CARD,
    SLOT_COVER_BACK,
    SLOT_DEFECTS,
    SLOT_ILLUSTRATIONS,
    classify_filename_to_slot,
)
from services.db_service import backup_db_to_s3
from services.ozon_service import (
    get_all_ozon_product_ids,
    get_products_attributes_batch,
    get_products_info_batch,
    parse_ozon_book_to_catalog,
)
from services.s3_service import get_s3_client, upload_bytes

_sync_status = {
    "running": False,
    "stage": "idle",
    "progress": 0,
    "total": 0,
    "uploaded_photos": 0,
    "skipped_books": 0,
    "new_ozon_cards": 0,
    "error": None,
    "done": False,
    "message": ""
}
_sync_lock = threading.Lock()


def get_smart_s3_sync_status() -> Dict[str, Any]:
    """Возвращает текущий прогресс фоновой умной синхронизации."""
    with _sync_lock:
        return dict(_sync_status)


def sanitize_folder_name(name: str, max_len: int = 50) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', '', name)
    cleaned = re.sub(r'[\s_]+', '_', cleaned).strip('._ ')
    return cleaned[:max_len] if cleaned else "Книга"


def download_bytes_resilient(url: str, retries: int = 3, timeout: int = 15) -> Optional[bytes]:
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return None

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BookinisticS3Sync/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 0:
                        return data
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.5)
    return None


def sync_single_book_photos(book_row: Tuple[str, str, str], s3_bucket: str) -> Dict[str, Any]:
    art, title, raw_data = book_row
    data = json.loads(raw_data) if raw_data else {}
    clean_art = art.strip()
    clean_title = sanitize_folder_name(title or data.get("title") or "Книга")
    folder_prefix = f"{clean_art}_{clean_title}"

    main_photo = data.get("main_photo_url") or ""
    add_photos_raw = data.get("add_photo_urls") or ""
    if isinstance(add_photos_raw, str):
        add_photos = [u.strip() for u in add_photos_raw.split() if u.strip()]
    elif isinstance(add_photos_raw, list):
        add_photos = [str(u).strip() for u in add_photos_raw if str(u).strip()]
    else:
        add_photos = []

    # Умная проверка: если главное фото и все доп. фото уже лежат в Yandex S3
    all_on_s3 = True
    if main_photo and "storage.yandexcloud.net" not in main_photo:
        all_on_s3 = False
    for u in add_photos:
        if "storage.yandexcloud.net" not in u:
            all_on_s3 = False
            break

    if all_on_s3 and main_photo:
        return {
            "article": clean_art,
            "status": "skipped_already_on_s3",
            "main_url": main_photo,
            "add_urls": add_photos,
            "uploaded_count": 0
        }

    new_main_url = main_photo
    new_add_urls = []
    uploaded = 0

    # 1. Загрузка главного фото в S3
    if main_photo:
        if "storage.yandexcloud.net" in main_photo:
            new_main_url = main_photo
        else:
            main_bytes = download_bytes_resilient(main_photo)
            if main_bytes:
                s3_key = f"{folder_prefix}/01_cover_front.jpg"
                s3_res = upload_bytes(s3_key, main_bytes, "image/jpeg")
                if s3_res:
                    new_main_url = s3_res
                    uploaded += 1

    # 2. Интеллектуальная классификация и загрузка дополнительных фото в S3
    import io
    from PIL import Image

    # Скачиваем все доп. фото в память и анализируем их габариты и роли
    downloaded_items = []
    for idx, u in enumerate(add_photos, 1):
        if not u:
            continue
        if "storage.yandexcloud.net" in u:
            downloaded_items.append({"url": u, "bytes": None, "is_s3": True, "is_card": False})
            continue

        b = download_bytes_resilient(u)
        is_promo_card = False
        if b:
            try:
                im = Image.open(io.BytesIO(b))
                w, h = im.size
                # Промо-карточка магазина "Другой Петербург" имеет размер 1254x1254 (квадрат)
                # и всегда располагается последним фото в карточке Ozon
                if (w == 1254 and h == 1254) or (idx == len(add_photos) and abs(w - h) < 5 and w >= 800):
                    is_promo_card = True
            except Exception:
                pass
        downloaded_items.append({"url": u, "bytes": b, "is_s3": False, "is_card": is_promo_card})

    # Структура слотов книги:
    # 1) Обложка — 01_cover_front.jpg
    # 2) Промо-карточка — 99_card.jpg
    # 3) Последнее фото книги перед промо-карточкой — 02_cover_back.jpg (задняя обложка)
    # 4) Промежуточные фото — 04_illustration_{i}.jpg (развороты, страницы, вклейки)
    # 5) Кадры с тегом дефекта — 05_defect_{i}.jpg

    has_card = len(downloaded_items) > 0 and downloaded_items[-1].get("is_card")
    book_items = downloaded_items[:-1] if has_card else downloaded_items

    categorized_plan = []
    if len(book_items) == 1:
        # Одно доп. фото — это задник книги
        categorized_plan.append((book_items[0], "02_cover_back.jpg"))
    elif len(book_items) > 1:
        cur_ill = 1
        cur_def = 1
        for itm in book_items[:-1]:
            u_str = itm["url"]
            target_slot = classify_filename_to_slot(u_str)
            if target_slot == SLOT_DEFECTS:
                categorized_plan.append((itm, f"05_defect_{cur_def}.jpg"))
                cur_def += 1
            else:
                categorized_plan.append((itm, f"04_illustration_{cur_ill}.jpg"))
                cur_ill += 1
        # Последнее фото книги — задник
        last_u = book_items[-1]["url"]
        last_slot = classify_filename_to_slot(last_u)
        if last_slot == SLOT_DEFECTS:
            categorized_plan.append((book_items[-1], f"05_defect_{cur_def}.jpg"))
        else:
            categorized_plan.append((book_items[-1], "02_cover_back.jpg"))

    if has_card:
        categorized_plan.append((downloaded_items[-1], "99_card.jpg"))

    for itm, fname in categorized_plan:
        if itm["is_s3"]:
            new_add_urls.append(itm["url"])
            continue

        b = itm["bytes"]
        if b:
            s3_key = f"{folder_prefix}/{fname}"
            s3_res = upload_bytes(s3_key, b, "image/jpeg")
            if s3_res:
                new_add_urls.append(s3_res)
                uploaded += 1
            else:
                new_add_urls.append(itm["url"])
        else:
            new_add_urls.append(itm["url"])

    # 3. Обновляем локальный словарь данных
    data["main_photo_url"] = new_main_url
    data["add_photo_urls"] = " ".join(new_add_urls)
    data["photo_main"] = new_main_url
    data["photos_additional"] = " ".join(new_add_urls)

    return {
        "article": clean_art,
        "status": "updated",
        "main_url": new_main_url,
        "add_urls": new_add_urls,
        "data_json": json.dumps(data, ensure_ascii=False),
        "uploaded_count": uploaded
    }


def run_smart_ozon_s3_sync(
    check_ozon_new: bool = True,
    max_workers: int = 15,
    limit: Optional[int] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Dict[str, Any]:
    """
    Основная синхронизация:
    1. Проверка новых карточек на Ozon
    2. Потоковая загрузка фото в S3 с обновлением catalog.db
    3. Резервное копирование catalog.db в Yandex S3
    """
    global _sync_status
    with _sync_lock:
        _sync_status["running"] = True
        _sync_status["done"] = False
        _sync_status["error"] = None
        _sync_status["progress"] = 0
        _sync_status["uploaded_photos"] = 0
        _sync_status["skipped_books"] = 0

    try:
        # Шаг 1: Проверка новых карточек
        new_cards_count = 0
        if check_ozon_new:
            with _sync_lock:
                _sync_status["stage"] = "checking_ozon"
                _sync_status["message"] = "Проверка новых карточек на Ozon..."
            if on_progress:
                on_progress(_sync_status)

            prod_items = get_all_ozon_product_ids(visibility="ALL")
            if prod_items:
                conn = sqlite3.connect(get_db_path())
                cursor = conn.cursor()
                cursor.execute("SELECT article FROM books")
                existing_articles = set(r[0] for r in cursor.fetchall())
                conn.close()

                new_items = [p for p in prod_items if (p.get("offer_id") or "").strip() not in existing_articles]
                if new_items:
                    batch_size = 100
                    for i in range(0, len(new_items), batch_size):
                        batch = new_items[i:i + batch_size]
                        offer_ids = [p["offer_id"] for p in batch if p.get("offer_id")]
                        p_ids = [p["product_id"] for p in batch if p.get("product_id")]

                        infos = get_products_info_batch(product_ids=p_ids, offer_ids=offer_ids)
                        info_by_art = {item.get("offer_id"): item for item in infos}

                        attrs = get_products_attributes_batch(product_ids=p_ids, offer_ids=offer_ids)
                        attr_by_art = {item.get("offer_id"): item for item in attrs}

                        conn = sqlite3.connect(get_db_path())
                        cur = conn.cursor()
                        for art in offer_ids:
                            it_info = info_by_art.get(art) or {}
                            it_attr = attr_by_art.get(art) or {}
                            if not it_info and not it_attr:
                                continue
                            parsed = parse_ozon_book_to_catalog(it_info, it_attr)
                            parsed["status"] = "imported"
                            title = parsed.get("title") or "Книга"
                            author = parsed.get("author") or ""
                            year = int(parsed.get("year") or 0) or None
                            price = float(parsed.get("price") or 0.0) or None
                            template_mode = parsed.get("template_mode") or "pre2011"
                            data_json = json.dumps(parsed, ensure_ascii=False)
                            cur.execute("""
                                INSERT OR REPLACE INTO books (article, title, author, year, price, template_mode, status, updated_at, data)
                                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
                            """, (art, title, author, year, price, template_mode, "imported", data_json))
                            new_cards_count += 1
                        conn.commit()
                        conn.close()

            with _sync_lock:
                _sync_status["new_ozon_cards"] = new_cards_count

        # Шаг 2: Потоковая выгрузка фото в S3
        with _sync_lock:
            _sync_status["stage"] = "syncing_photos"
            _sync_status["message"] = "Синхронизация фотографий с Yandex S3..."

        s3_client, bucket = get_s3_client()
        if not s3_client or not bucket:
            raise RuntimeError("Yandex S3 не настроен или учетные данные недействительны")

        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT article, title, data FROM books")
        rows = cursor.fetchall()
        conn.close()

        if limit and limit > 0:
            rows = rows[:limit]

        need_sync_rows = []
        already_s3_count = 0
        for r in rows:
            data = json.loads(r[2]) if r[2] else {}
            mp = data.get("main_photo_url") or ""
            if mp and "storage.yandexcloud.net" in mp:
                already_s3_count += 1
            else:
                need_sync_rows.append(r)

        with _sync_lock:
            _sync_status["total"] = len(need_sync_rows)
            _sync_status["skipped_books"] = already_s3_count

        if need_sync_rows:
            completed = 0
            uploaded_total = 0
            pending_updates = []

            def _flush_batch_to_db(batch):
                if not batch:
                    return
                c = sqlite3.connect(get_db_path())
                cur = c.cursor()
                for item in batch:
                    cur.execute("""
                        UPDATE books
                        SET updated_at = datetime('now'),
                            data = ?
                        WHERE article = ?
                    """, (item["data_json"], item["article"]))
                c.commit()
                c.close()

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(sync_single_book_photos, r, bucket): r[0] for r in need_sync_rows}
                for future in as_completed(futures):
                    res = future.result()
                    completed += 1
                    if res.get("status") == "updated":
                        uploaded_total += res.get("uploaded_count", 0)
                        pending_updates.append(res)

                    if len(pending_updates) >= 25:
                        _flush_batch_to_db(pending_updates)
                        pending_updates.clear()

                    with _sync_lock:
                        _sync_status["progress"] = completed
                        _sync_status["uploaded_photos"] = uploaded_total
                        _sync_status["message"] = f"Синхронизировано книг: {completed}/{len(need_sync_rows)} ({uploaded_total} фото в S3)"

                    if on_progress:
                        on_progress(_sync_status)

            if pending_updates:
                _flush_batch_to_db(pending_updates)
                pending_updates.clear()

        # Шаг 3: Резервное копирование базы в S3
        with _sync_lock:
            _sync_status["stage"] = "backup_db"
            _sync_status["message"] = "Резервное копирование catalog.db в Yandex S3..."
        if on_progress:
            on_progress(_sync_status)

        backup_res = backup_db_to_s3()

        with _sync_lock:
            _sync_status["stage"] = "finished"
            _sync_status["done"] = True
            _sync_status["running"] = False
            _sync_status["message"] = "Синхронизация успешно завершена!"
            _sync_status["backup"] = backup_res

        return dict(_sync_status)

    except Exception as e:
        with _sync_lock:
            _sync_status["running"] = False
            _sync_status["error"] = str(e)
            _sync_status["message"] = f"Ошибка синхронизации: {e}"
        raise


def start_smart_s3_sync_async(check_ozon_new: bool = True, max_workers: int = 15) -> Dict[str, Any]:
    """Запускает процесс умной синхронизации в отдельном потоке-демоне."""
    with _sync_lock:
        if _sync_status.get("running"):
            return {"success": False, "error": "Синхронизация уже выполняется"}

    def _worker():
        try:
            run_smart_ozon_s3_sync(check_ozon_new=check_ozon_new, max_workers=max_workers)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True, name="smart_s3_sync_worker")
    t.start()
    return {"success": True, "message": "Умная синхронизация запущена в фоновом режиме"}

