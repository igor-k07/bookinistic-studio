"""
db_service.py: Локальная база данных SQLite для каталога книг Bookinistic.
Использует гибридную схему: ключевые поля для быстрого поиска + полный JSON-документ книги.
"""

from datetime import datetime
import json
import os
import re
import sqlite3
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


def save_book_to_db(book: Dict[str, Any]) -> Dict[str, Any]:
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

