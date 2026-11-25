"""SQLite Unit of Work and versioned database migrations.

Implements ADR-1 (SQLite WAL + FTS5), Strict Engineering Guardrails #2 (no raw sqlite3 without close)
and #3 (migrations run strictly once at startup, never inside CRUD).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, List, Optional, Union

logger = logging.getLogger(__name__)

DEFAULT_BRANDS: List[str] = [
    "Нет бренда", "Наука", "Художественная литература", "Просвещение", "Детская литература",
    "Мир", "Советский писатель", "Правда", "Молодая гвардия", "Мысль", "Политиздат",
    "Искусство", "Лениздат", "АСТ", "Эксмо", "Азбука", "Питер", "Амфора", "Терра",
    "Северо-Запад", "Радуга", "Прогресс", "Высшая школа", "Недра", "Машиностроение",
    "Химия", "Медицина", "Колос", "Транспорт", "Физкультура и спорт", "Музыка",
]


class SqliteUnitOfWork:
    """Context manager for SQLite connections guaranteeing close in finally."""

    def __init__(self, db_path: Union[str, Path]) -> None:
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._in_transaction = False
        self._depth = 0

    def __enter__(self) -> "SqliteUnitOfWork":
        self._depth += 1
        if self._depth == 1:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                isolation_level=None,  # Explicit transaction management
            )
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.execute("PRAGMA synchronous = NORMAL;")
            self.conn.execute("PRAGMA foreign_keys = ON;")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Optional[bool]:
        self._depth -= 1
        if self._depth <= 0:
            self._depth = 0
            try:
                if self.conn:
                    if exc_type is not None and self._in_transaction:
                        try:
                            self.conn.execute("ROLLBACK;")
                        except Exception:
                            pass
                    elif self._in_transaction:
                        try:
                            self.conn.execute("COMMIT;")
                        except Exception:
                            pass
            finally:
                if self.conn:
                    try:
                        self.conn.close()
                    except Exception:
                        pass
                    self.conn = None
                    self._in_transaction = False
        return None

    def begin(self) -> None:
        """Begin an immediate write transaction."""
        if not self.conn:
            raise RuntimeError("Database connection not opened")
        if not self._in_transaction:
            self.conn.execute("BEGIN IMMEDIATE;")
            self._in_transaction = True

    def commit(self) -> None:
        """Commit active transaction."""
        if self.conn and self._in_transaction:
            self.conn.execute("COMMIT;")
            self._in_transaction = False

    def rollback(self) -> None:
        """Rollback active transaction."""
        if self.conn and self._in_transaction:
            self.conn.execute("ROLLBACK;")
            self._in_transaction = False

    def execute(self, sql: str, params: Union[tuple, dict] = ()) -> sqlite3.Cursor:
        """Execute SQL query."""
        if not self.conn:
            raise RuntimeError("Database connection not opened")
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: Any) -> sqlite3.Cursor:
        """Execute batch SQL queries."""
        if not self.conn:
            raise RuntimeError("Database connection not opened")
        return self.conn.executemany(sql, seq_of_params)


def run_migrations(db_path: Union[str, Path]) -> None:
    """Execute SQLite schema migrations up to target version (user_version = 1).

    Non-destructive: preserves existing books, assets, and fills FTS5 and sequences.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with SqliteUnitOfWork(path) as uow:
        assert uow.conn is not None
        cursor = uow.execute("PRAGMA user_version;")
        current_version = cursor.fetchone()[0]

        if current_version < 1:
            logger.info(f"Migrating database {path} to version 1...")
            uow.begin()
            _migrate_to_v1(uow.conn)
            uow.execute("PRAGMA user_version = 1;")
            uow.commit()
            logger.info(f"Database {path} successfully migrated to version 1.")


def _migrate_to_v1(conn: sqlite3.Connection) -> None:
    """Migration 1: Reference 2.0 schema, FTS5 sync, sequences and reference brands."""
    # 1. Inspect existing books table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='books';")
    books_exist = cursor.fetchone() is not None

    if not books_exist:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                article          TEXT PRIMARY KEY COLLATE NOCASE,
                title            TEXT NOT NULL DEFAULT '',
                author           TEXT NOT NULL DEFAULT 'не указан',
                year             INTEGER,
                price            REAL,
                template_mode    TEXT NOT NULL DEFAULT 'pre2011',
                status           TEXT NOT NULL DEFAULT 'DRAFT',
                storage_location TEXT NOT NULL DEFAULT '',
                data_json        TEXT NOT NULL DEFAULT '{}',
                created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
    else:
        # Check existing columns
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(books);").fetchall()}
        if "data_json" not in cols and "data" in cols:
            conn.execute("ALTER TABLE books ADD COLUMN data_json TEXT NOT NULL DEFAULT '{}';")
            conn.execute("UPDATE books SET data_json = data WHERE data IS NOT NULL AND data != '';")
        if "storage_location" not in cols:
            conn.execute("ALTER TABLE books ADD COLUMN storage_location TEXT NOT NULL DEFAULT '';")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_mode ON books(template_mode);")

    # 2. FTS5 Virtual Table & Triggers (Standalone FTS5 table)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
            article, title, author, publisher, series, isbn
        );
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
            INSERT INTO books_fts(article, title, author, publisher, series, isbn)
            VALUES (
                new.article, new.title, new.author,
                json_extract(new.data_json, '$.publisher'),
                json_extract(new.data_json, '$.series'),
                json_extract(new.data_json, '$.isbn')
            );
        END;
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
            DELETE FROM books_fts WHERE article = old.article;
        END;
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
            DELETE FROM books_fts WHERE article = old.article;
            INSERT INTO books_fts(article, title, author, publisher, series, isbn)
            VALUES (
                new.article, new.title, new.author,
                json_extract(new.data_json, '$.publisher'),
                json_extract(new.data_json, '$.series'),
                json_extract(new.data_json, '$.isbn')
            );
        END;
    """)

    # Populate FTS5 if currently empty
    fts_count = conn.execute("SELECT COUNT(*) FROM books_fts;").fetchone()[0]
    if fts_count == 0:
        conn.execute("""
            INSERT INTO books_fts(article, title, author, publisher, series, isbn)
            SELECT
                article, title, author,
                json_extract(data_json, '$.publisher'),
                json_extract(data_json, '$.series'),
                json_extract(data_json, '$.isbn')
            FROM books;
        """)

    # 3. Workspace Tabs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workspace_tabs (
            id               TEXT PRIMARY KEY,
            book_article     TEXT NOT NULL REFERENCES books(article) ON DELETE CASCADE,
            tab_order        INTEGER NOT NULL DEFAULT 0,
            is_active        INTEGER NOT NULL DEFAULT 0,
            is_edit_mode     INTEGER NOT NULL DEFAULT 0,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 4. Assets Table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assets';")
    assets_exist = cursor.fetchone() is not None

    if not assets_exist:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id                TEXT PRIMARY KEY,
                book_article      TEXT REFERENCES books(article) ON DELETE SET NULL,
                slot              TEXT,
                slot_order        INTEGER NOT NULL DEFAULT 0,
                status            TEXT NOT NULL DEFAULT 'UPLOADED',
                status_message    TEXT NOT NULL DEFAULT '',
                original_path     TEXT NOT NULL,
                preview_path      TEXT NOT NULL,
                ai_white_path     TEXT,
                transformations   TEXT NOT NULL DEFAULT '{}',
                render_hash       TEXT NOT NULL DEFAULT '',
                s3_staging_url    TEXT,
                s3_final_url      TEXT,
                s3_uploaded_hash  TEXT,
                version           INTEGER NOT NULL DEFAULT 1,
                width             INTEGER NOT NULL DEFAULT 0,
                height            INTEGER NOT NULL DEFAULT 0,
                file_size_bytes   INTEGER NOT NULL DEFAULT 0,
                created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
    else:
        asset_cols = {row["name"] for row in conn.execute("PRAGMA table_info(assets);").fetchall()}
        if "render_hash" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN render_hash TEXT NOT NULL DEFAULT '';")
        if "s3_staging_url" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN s3_staging_url TEXT;")
        if "s3_final_url" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN s3_final_url TEXT;")
            if "s3_url" in asset_cols:
                conn.execute("UPDATE assets SET s3_final_url = s3_url WHERE s3_url IS NOT NULL;")
        if "s3_uploaded_hash" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN s3_uploaded_hash TEXT;")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_book ON assets(book_article);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);")

    # 5. Sequences Table (Atomic Article Counters)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sequences (
            name             TEXT PRIMARY KEY,
            next_val         INTEGER NOT NULL
        );
    """)

    # Determine max article sequence from books to eliminate the >10000 bug
    max_num = 1
    for row in conn.execute("SELECT article FROM books;").fetchall():
        art_str = str(row["article"] or "")
        m = re.search(r"(\d+)", art_str)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num

    conn.execute(
        "INSERT OR IGNORE INTO sequences (name, next_val) VALUES ('article_dp_b', ?);",
        (max_num + 1,),
    )

    # 6. Marketplace Transactional Outbox
    conn.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_outbox (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            channel          TEXT NOT NULL DEFAULT 'ozon',
            book_article     TEXT NOT NULL REFERENCES books(article) ON DELETE CASCADE,
            action           TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'QUEUED',
            external_task_id TEXT,
            attempts         INTEGER NOT NULL DEFAULT 0,
            next_retry_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_error       TEXT NOT NULL DEFAULT '',
            error_fields     TEXT NOT NULL DEFAULT '[]',
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outbox_status ON marketplace_outbox(status, next_retry_at);")

    # 7. Reference Brands and Enrichment Cache
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reference_brands (
            name            TEXT PRIMARY KEY,
            name_normalized TEXT NOT NULL DEFAULT ''
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ref_brands_norm ON reference_brands(name_normalized);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enrichment_cache (
            cache_key        TEXT PRIMARY KEY,
            provider         TEXT NOT NULL,
            payload_json     TEXT NOT NULL,
            expires_at       INTEGER NOT NULL
        );
    """)

    # Seed reference brands from DEFAULT_BRANDS and books
    for brand in DEFAULT_BRANDS:
        conn.execute(
            "INSERT OR IGNORE INTO reference_brands (name, name_normalized) VALUES (?, ?);",
            (brand, brand.strip().lower()),
        )

    # Seed verified brands from existing catalog
    for row in conn.execute("SELECT data_json FROM books;").fetchall():
        try:
            d = json.loads(row["data_json"] or "{}")
            b = str(d.get("brand") or "").strip()
            if b:
                conn.execute(
                    "INSERT OR IGNORE INTO reference_brands (name, name_normalized) VALUES (?, ?);",
                    (b, b.lower()),
                )
        except Exception:
            pass
