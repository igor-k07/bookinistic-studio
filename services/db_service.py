"""
db_service.py: Локальная база данных SQLite для каталога книг Bookinistic.
Использует гибридную схему: ключевые поля для быстрого поиска + полный JSON-документ книги.
"""

from datetime import datetime
import json
import os
import re
import sqlite3
import tempfile
import threading
from typing import Any, Dict, List, Optional

from config import DB_PATH, READY_TABLES_DIR


def get_db_connection() -> sqlite3.Connection:
    """Возвращает соединение с базой данных SQLite в режиме WAL."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db():
    """Инициализирует структуру таблиц и индексов в базе данных."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                article         TEXT PRIMARY KEY,
                title           TEXT NOT NULL,
                author          TEXT,
                year            INTEGER,
                price           REAL,
                template_mode   TEXT DEFAULT 'pre2011',
                status          TEXT DEFAULT 'ready',
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                data            TEXT NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_books_mode ON books(template_mode);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_books_created ON books(created_at);")
        conn.commit()


def clean_book_data_for_db(book: Dict[str, Any]) -> Dict[str, Any]:
    """
    Очищает словарь книги от тяжелых base64-строк перед записью в JSON базы данных
    (фото сохраняются в хранилище books_vault и Yandex S3, в БД хранятся ссылки и имена файлов).
    """
    clean = dict(book)
    # Правило: плашка-предупреждение вставляется ТОЛЬКО если есть фото мантры / дефектов (слот 5)
    warning_prefix = "ВНИМАНИЕ! КНИГА НЕ НОВАЯ. Имеются определённые нюансы (повреждения) см. дополнительные фото."
    slots_photos_raw = clean.get("slots_photos") or {}
    mantra_photos = slots_photos_raw.get("mantra_defects") or []
    has_mantra_defects = bool(mantra_photos) or bool(clean.get("has_mantra_defects"))
    ant = str(clean.get("annotation") or "").strip()
    if warning_prefix in ant:
        ant = ant.replace(warning_prefix, "").strip()
    if has_mantra_defects and ant:
        ant = (warning_prefix + "\n\n" + ant).strip()
    clean["annotation"] = ant

    # Санитизация возрастного ценза: только строго допустимые значения, иначе пустая строка
    raw_age = str(clean.get("age_limit") or "").strip()
    if raw_age not in ("0+", "6+", "12+", "16+", "18+"):
        clean["age_limit"] = ""

    # Если в slots_photos были base64-данные, сохраняем только имена файлов
    if "slots_photos" in clean and isinstance(clean["slots_photos"], dict):
        compact_slots = {}
        for slot, item in clean["slots_photos"].items():
            if isinstance(item, dict):
                compact_slots[slot] = {"name": item.get("name", "photo.jpg")}
            elif isinstance(item, list):
                compact_slots[slot] = [{"name": p.get("name", "photo.jpg")} for p in item if isinstance(p, dict)]
            else:
                compact_slots[slot] = item
        clean["slots_photos"] = compact_slots
    return clean


def save_book_to_db(book: Dict[str, Any], sync_s3: bool = True) -> Dict[str, Any]:
    """
    Сохраняет или обновляет книгу в базе данных SQLite (UPSERT).
    """
    init_db()
    article = str(book.get("article") or "").strip()
    if not article:
        article = get_next_article_number()
        book["article"] = article

    title = str(book.get("title") or "Без названия").strip()
    author = str(book.get("author") or book.get("author_cover") or "").strip()

    year_val = None
    try:
        y_str = str(book.get("year") or "").strip()
        y_match = re.findall(r"\d{4}", y_str)
        if y_match:
            year_val = int(y_match[0])
    except Exception:
        pass

    price_val = 0.0
    try:
        price_val = float(str(book.get("price") or 0).replace(" ", "").replace(",", "."))
    except Exception:
        pass

    mode = str(book.get("template_mode") or "").strip()
    if not mode:
        mode = "pre2011" if (year_val and year_val <= 2011) else "post2011"
        book["template_mode"] = mode

    status = str(book.get("status") or "ready").strip()
    clean_data = clean_book_data_for_db(book)
    data_json = json.dumps(clean_data, ensure_ascii=False)

    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO books (
                article, title, author, year, price, template_mode, status, updated_at, data
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?
            )
            ON CONFLICT(article) DO UPDATE SET
                title = excluded.title,
                author = excluded.author,
                year = excluded.year,
                price = excluded.price,
                template_mode = excluded.template_mode,
                status = excluded.status,
                updated_at = datetime('now'),
                data = excluded.data;
        """, (article, title, author, year_val, price_val, mode, status, data_json))
        conn.commit()

    invalidate_references_cache()

    # Асинхронная синхронизация базы в Yandex S3 (в фоне, не тормозит ответ)
    if sync_s3:
        backup_db_to_s3_async()

    return book


def get_book_from_db(article: str) -> Optional[Dict[str, Any]]:
    """Возвращает полный словарь книги по её артикулу."""
    init_db()
    target_art = str(article or "").strip()
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM books WHERE article = ? COLLATE NOCASE", (target_art,)).fetchone()
        if not row:
            return None
        try:
            full_data = json.loads(row["data"])
        except Exception:
            full_data = {}
        full_data["article"] = row["article"]
        full_data["title"] = row["title"]
        full_data["author"] = row["author"]
        full_data["year"] = row["year"]
        full_data["price"] = row["price"]
        full_data["template_mode"] = row["template_mode"]
        full_data["status"] = row["status"]
        full_data["created_at"] = row["created_at"]
        return full_data


def delete_book_from_db(article: str) -> bool:
    """Удаляет книгу из базы данных по её артикулу."""
    init_db()
    target_art = str(article or "").strip()
    with get_db_connection() as conn:
        cursor = conn.execute("DELETE FROM books WHERE article = ? COLLATE NOCASE", (target_art,))
        conn.commit()
        if cursor.rowcount > 0:
            backup_db_to_s3_async()
        return cursor.rowcount > 0


def get_all_books_from_db(
    mode: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Возвращает список книг из базы данных с опциональной фильтрацией по режиму Ozon, статусу и поиску.
    """
    init_db()
    query = "SELECT * FROM books WHERE 1=1"
    params = []

    if mode:
        query += " AND template_mode = ?"
        params.append(mode)

    if status:
        query += " AND status = ?"
        params.append(status)

    if search:
        s_like = f"%{search.strip()}%"
        query += " AND (title LIKE ? OR author LIKE ? OR article LIKE ?)"
        params.extend([s_like, s_like, s_like])

    query += " ORDER BY article ASC"

    result = []
    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        for idx, row in enumerate(rows, 1):
            try:
                b = json.loads(row["data"])
            except Exception:
                b = {}
            b["num"] = idx
            b["article"] = row["article"]
            b["title"] = row["title"]
            b["author"] = row["author"]
            b["year"] = row["year"]
            b["price"] = row["price"]
            b["template_mode"] = row["template_mode"]
            b["status"] = row["status"]
            b["created_at"] = row["created_at"]
            result.append(b)

    return result


def get_next_article_number() -> str:
    """
    Определяет следующий свободный номер артикула (DP-B-xxxxx) на основе всех книг в базе
    и существующих архивов в books_vault.
    """
    init_db()
    max_num = 2600

    # 1. Проверяем записи в базе данных
    try:
        with get_db_connection() as conn:
            rows = conn.execute("SELECT article FROM books").fetchall()
            for r in rows:
                art = str(r["article"] or "").strip()
                digits = re.findall(r"\d+", art)
                if digits:
                    val = int(digits[-1])
                    # Защита от опечаток с лишними нулями в Ozon вроде DP-B-025013 вместо 02513
                    if val > 10000:
                        continue
                    if val > max_num:
                        max_num = val
    except Exception:
        pass

    # 2. Проверяем локальные папки в storage/books_vault
    from config import VAULT_DIR
    if os.path.exists(VAULT_DIR):
        for fname in os.listdir(VAULT_DIR):
            if fname.startswith("DP-B-"):
                digits = re.findall(r"\d+", fname)
                if digits:
                    try:
                        val = int(digits[0])
                        if val > 10000:
                            continue
                        if val > max_num:
                            max_num = val
                    except Exception:
                        pass

    return f"DP-B-{(max_num + 1):05d}"


def migrate_existing_excel_to_db():
    """
    Сканирует существующие файлы таблиц Excel в ready_tables/ и импортирует книги в базу SQLite,
    если они ещё не были добавлены.
    """
    from services.excel_service import get_current_books

    init_db()
    imported_count = 0
    for mode in ["pre2011", "post2011"]:
        try:
            excel_books = get_current_books(mode)
            for b in excel_books:
                art = b.get("article")
                if art:
                    existing = get_book_from_db(art)
                    if not existing:
                        b["template_mode"] = mode
                        b["status"] = "exported"
                        save_book_to_db(b)
                        imported_count += 1
        except Exception as e:
            print(f"[DB:Migration] Ошибка миграции {mode}: {e}")

    if imported_count > 0:
        print(f"📦 [DB:Migration] Успешно импортировано {imported_count} книг из существующих таблиц в базу catalog.db!")
    return imported_count


# =========================================================================
# Синхронизация и резервное копирование SQLite в Yandex Object Storage (S3)
# =========================================================================

_last_s3_sync: Dict[str, Any] = {
    "last_sync": None,
    "status": "idle",
    "size_bytes": 0,
    "latest_url": None,
    "error": None,
}
_sync_lock = threading.Lock()
_backup_timer: Optional[threading.Timer] = None
_timer_lock = threading.Lock()


def get_db_sync_status() -> Dict[str, Any]:
    """Возвращает информацию о последней синхронизации базы с Yandex S3."""
    return dict(_last_s3_sync)


def backup_db_to_s3_async(delay: float = 2.0):
    """
    Запускает бэкап базы в Yandex S3 в фоновом потоке с дебаунсом (задержка 2 сек),
    чтобы объединять частые сохранения книг в один быстрый сетевой запрос.
    """
    global _backup_timer
    with _timer_lock:
        if _backup_timer is not None:
            _backup_timer.cancel()
        _backup_timer = threading.Timer(delay, backup_db_to_s3)
        _backup_timer.daemon = True
        _backup_timer.start()


def backup_db_to_s3() -> Dict[str, Any]:
    """
    Создает атомарный консистентный снимок SQLite базы и выгружает его в Yandex S3:
    1. backups/db/catalog_latest.db (всегда актуальная копия)
    2. backups/db/history/catalog_YYYY-MM-DD.db (суточный исторический архив)
    """
    from services.s3_service import get_s3_client
    global _last_s3_sync

    client, bucket = get_s3_client()
    if not client or not bucket:
        _last_s3_sync["status"] = "skipped_no_s3"
        return {"ok": False, "error": "S3 not configured"}

    if not os.path.exists(DB_PATH):
        return {"ok": False, "error": "Database file does not exist"}

    with _sync_lock:
        _last_s3_sync["status"] = "syncing"
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Атомарный безопасный снимок без блокировки чтения и записи
            with sqlite3.connect(DB_PATH) as src, sqlite3.connect(tmp_path) as dst:
                src.backup(dst)

            with open(tmp_path, "rb") as f:
                db_bytes = f.read()

            today_str = datetime.now().strftime("%Y-%m-%d")
            latest_key = "backups/db/catalog_latest.db"
            history_key = f"backups/db/history/catalog_{today_str}.db"

            # 1. Загрузка актуального слепка
            client.put_object(
                Bucket=bucket,
                Key=latest_key,
                Body=db_bytes,
                ContentType="application/x-sqlite3",
                CacheControl="no-cache",
            )
            latest_url = f"https://storage.yandexcloud.net/{bucket}/{latest_key}"

            # 2. Загрузка суточного исторического архива
            client.put_object(
                Bucket=bucket,
                Key=history_key,
                Body=db_bytes,
                ContentType="application/x-sqlite3",
                CacheControl="public, max-age=86400",
            )

            iso_now = datetime.now().isoformat()
            _last_s3_sync = {
                "last_sync": iso_now,
                "status": "synced",
                "size_bytes": len(db_bytes),
                "latest_url": latest_url,
                "history_key": history_key,
                "error": None,
            }
            print(f"☁️ [DB:S3] База catalog.db синхронизирована с S3 ({len(db_bytes)} байт) -> {latest_key}")
            return {"ok": True, "data": _last_s3_sync}

        except Exception as e:
            err_msg = str(e)
            print(f"⚠️ [DB:S3] Ошибка бэкапа базы в S3: {err_msg}")
            _last_s3_sync["status"] = "error"
            _last_s3_sync["error"] = err_msg
            return {"ok": False, "error": err_msg}
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


def restore_db_from_s3() -> Dict[str, Any]:
    """
    Восстанавливает локальную базу catalog.db из backups/db/catalog_latest.db в Yandex S3.
    Перед заменой создает локальную резервную копию catalog.db.bak.
    """
    from services.s3_service import get_s3_client
    import shutil

    client, bucket = get_s3_client()
    if not client or not bucket:
        return {"ok": False, "error": "S3 not configured"}

    latest_key = "backups/db/catalog_latest.db"
    try:
        response = client.get_object(Bucket=bucket, Key=latest_key)
        content = response["Body"].read()

        if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
            shutil.copyfile(DB_PATH, DB_PATH + ".bak")

        with open(DB_PATH, "wb") as f:
            f.write(content)

        print(f"📥 [DB:S3] База данных успешно восстановлена из S3 ({len(content)} байт)")
        return {"ok": True, "size_bytes": len(content)}
    except Exception as e:
        err_msg = str(e)
        print(f"⚠️ [DB:S3] Ошибка восстановления базы из S3: {err_msg}")
        return {"ok": False, "error": err_msg}


# -------------------------------------------------------------
# КАТАЛОГ ЭТАЛОННЫХ ЗНАЧЕНИЙ И СВЕРКА (КАНАНИЗАЦИЯ)
# -------------------------------------------------------------

_REF_CACHE = None
_REF_CACHE_TIME = 0.0


def invalidate_references_cache():
    """Сбрасывает кэш эталонных справочников при добавлении новой книги."""
    global _REF_CACHE
    _REF_CACHE = None


def get_catalog_references(force_reload: bool = False) -> Dict[str, List[str]]:
    """
    Возвращает уникальные эталонные списки значений из базы данных catalog.db:
    авторы, переводчики, иллюстраторы, издательства, серии, бренды.
    """
    global _REF_CACHE, _REF_CACHE_TIME
    import time
    now = time.time()
    if not force_reload and _REF_CACHE is not None and (now - _REF_CACHE_TIME < 300):
        return _REF_CACHE

    init_db()
    with get_db_connection() as conn:
        rows = conn.execute("SELECT data FROM books").fetchall()

    authors_set = set()
    translators_set = set()
    illustrators_set = set()
    publishers_set = set()
    series_set = set()
    brands_set = set()

    for r in rows:
        try:
            d = json.loads(r["data"])
        except Exception:
            continue

        raw_author = str(d.get("author") or "").strip()
        for a in raw_author.split(";"):
            a = a.strip()
            if a and a.lower() not in ("не указан", "нет автора", "none", "null"):
                authors_set.add(a)

        raw_trans = str(d.get("translator") or "").strip()
        for t in raw_trans.split(";"):
            t = t.strip()
            if t and t.lower() not in ("не указан", "нет", "none"):
                translators_set.add(t)

        raw_ill = str(d.get("illustrator") or "").strip()
        for ill in raw_ill.split(";"):
            ill = ill.strip()
            if ill and ill.lower() not in ("не указан", "нет", "none"):
                illustrators_set.add(ill)

        pub = str(d.get("publisher") or "").strip()
        if pub and pub.lower() not in ("none", "null"):
            publishers_set.add(pub)

        ser = str(d.get("series") or "").strip()
        if ser and ser.lower() not in ("none", "null"):
            series_set.add(ser)

        br = str(d.get("brand") or "").strip()
        if br and br.lower() not in ("none", "null"):
            brands_set.add(br)

    brands_set.add("Нет бренда")

    # Сортировка: бренды с "Нет бренда" на первом месте
    sorted_brands = sorted(list(brands_set), key=lambda x: (x != "Нет бренда", x.lower()))

    _REF_CACHE = {
        "authors": sorted(list(authors_set), key=lambda x: x.lower()),
        "translators": sorted(list(translators_set), key=lambda x: x.lower()),
        "illustrators": sorted(list(illustrators_set), key=lambda x: x.lower()),
        "publishers": sorted(list(publishers_set), key=lambda x: x.lower()),
        "series": sorted(list(series_set), key=lambda x: x.lower()),
        "brands": sorted_brands,
    }
    _REF_CACHE_TIME = now
    return _REF_CACHE


def _match_person(name: str, known_list: List[str]) -> str:
    """
    Сверяет имя персоны (автор/переводчик/иллюстратор) со списком из базы.
    Поддерживает: точное совпадение, нечувствительность к регистру,
    сопоставление инициалов с полным ФИО (например, Толстой Л. Н. -> Толстой Лев Николаевич).
    Если совпадение не найдено, возвращает исходное имя.
    """
    clean = name.strip()
    if not clean or clean.lower() in ("не указан", "нет автора", "—", "-"):
        return clean

    lower_map = {p.lower(): p for p in known_list}
    if clean.lower() in lower_map:
        return lower_map[clean.lower()]

    parts = clean.replace(".", ". ").split()
    if not parts:
        return clean
    surname = parts[0].lower()

    candidates = [p for p in known_list if p.lower().startswith(surname + " ")]
    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1 and len(parts) >= 2:
        # Сверяем первую букву имени
        first_init = parts[1][0].lower()
        sub_cands = []
        for c in candidates:
            c_parts = c.split()
            if len(c_parts) >= 2 and c_parts[1][0].lower() == first_init:
                sub_cands.append(c)
        if len(sub_cands) == 1:
            return sub_cands[0]

    return clean


def _match_title_or_org(val: str, known_list: List[str]) -> str:
    """
    Сверяет название издательства или серии с базой (без учета регистра и внешних кавычек).
    """
    clean = val.strip().strip('"\'«»')
    if not clean:
        return val

    lower_map = {p.strip().strip('"\'«»').lower(): p for p in known_list}
    if clean.lower() in lower_map:
        return lower_map[clean.lower()]

    return val


def reconcile_with_references(book_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Канонизирует распознанные ИИ поля на основе накопленной базы данных магазина (catalog.db):
    автор официальный, переводчик, иллюстратор, издательство, серия, бренд.
    Если значение новое (нет в базе) — сохраняет как есть по старым правилам.
    """
    if not isinstance(book_data, dict):
        return book_data

    refs = get_catalog_references()
    authors_ref = refs.get("authors", [])
    translators_ref = refs.get("translators", [])
    illustrators_ref = refs.get("illustrators", [])
    publishers_ref = refs.get("publishers", [])
    series_ref = refs.get("series", [])
    brands_ref = refs.get("brands", [])

    # 1. Автор официальный (author)
    raw_author = str(book_data.get("author") or "").strip()
    if raw_author and raw_author.lower() not in ("не указан", "нет автора"):
        matched_authors = []
        for part in raw_author.split(";"):
            m = _match_person(part, authors_ref)
            matched_authors.append(m)
        book_data["author"] = ";".join(matched_authors)

    # 2. Переводчик (translator)
    raw_trans = str(book_data.get("translator") or "").strip()
    if raw_trans and raw_trans.lower() not in ("не указан", "нет"):
        matched_trans = []
        for part in raw_trans.split(";"):
            m = _match_person(part, translators_ref)
            matched_trans.append(m)
        book_data["translator"] = ";".join(matched_trans)

    # 3. Иллюстратор (illustrator)
    raw_ill = str(book_data.get("illustrator") or "").strip()
    if raw_ill and raw_ill.lower() not in ("не указан", "нет"):
        matched_ills = []
        for part in raw_ill.split(";"):
            m = _match_person(part, illustrators_ref)
            matched_ills.append(m)
        book_data["illustrator"] = ";".join(matched_ills)

    # 4. Издательство (publisher)
    raw_pub = str(book_data.get("publisher") or "").strip()
    if raw_pub:
        book_data["publisher"] = _match_title_or_org(raw_pub, publishers_ref)

    # 5. Серия (series)
    raw_ser = str(book_data.get("series") or "").strip()
    if raw_ser:
        book_data["series"] = _match_title_or_org(raw_ser, series_ref)

    # 6. Бренд (brand)
    raw_brand = str(book_data.get("brand") or "").strip()
    if raw_brand:
        canon_brand = _match_title_or_org(raw_brand, brands_ref)
        # Если бренд найден в Ozon-справочнике — ставим его
        brands_lower = {b.lower(): b for b in brands_ref}
        if canon_brand.lower() in brands_lower:
            book_data["brand"] = brands_lower[canon_brand.lower()]
        else:
            # Если бренд не распознан среди официальных — ставим "Нет бренда"
            book_data["brand"] = "Нет бренда"
    else:
        # Проверяем, может ли издательство книги быть брендом
        pub_cand = str(book_data.get("publisher") or "").strip()
        brands_lower = {b.lower(): b for b in brands_ref}
        if pub_cand.lower() in brands_lower:
            book_data["brand"] = brands_lower[pub_cand.lower()]
        else:
            book_data["brand"] = "Нет бренда"

    return book_data



