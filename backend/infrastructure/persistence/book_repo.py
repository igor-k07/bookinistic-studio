"""SQLite implementation of BookRepository, WorkspaceTab management, and Sequences.

Implements ADR-1 (WAL + FTS5), ADR-9 (Drafts in SQLite), and eliminating article ceiling bug.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from backend.domain.models import Book, WorkspaceTab
from backend.domain.ports import IBookRepository
from backend.infrastructure.persistence.sqlite_uow import SqliteUnitOfWork


class SqliteBookRepository(IBookRepository):
    """SQLite repository for Books, WorkspaceTabs, and atomic sequence numbers."""

    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self.uow = uow

    def get_by_article(self, article: str) -> Optional[Book]:
        """Fetch book by article."""
        cursor = self.uow.execute(
            "SELECT article, title, author, year, price, template_mode, status, "
            "storage_location, data_json, created_at, updated_at "
            "FROM books WHERE article = ? COLLATE NOCASE;",
            (article,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        data = json.loads(row["data_json"] or "{}")
        # Ensure row-level fields override json if diverged
        data["article"] = row["article"]
        data["title"] = row["title"]
        data["author"] = row["author"]
        data["year"] = row["year"]
        data["price"] = row["price"]
        data["template_mode"] = row["template_mode"]
        data["status"] = row["status"]
        data["storage_location"] = row["storage_location"]
        data["created_at"] = str(row["created_at"])
        data["updated_at"] = str(row["updated_at"])

        return Book.from_dict(data)

    def save(self, book: Book) -> None:
        """Atomically persist or update a Book."""
        data_dict = book.to_dict()
        data_json = json.dumps(data_dict, ensure_ascii=False)

        sql = """
            INSERT INTO books (
                article, title, author, year, price, template_mode,
                status, storage_location, data_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(article) DO UPDATE SET
                title = excluded.title,
                author = excluded.author,
                year = excluded.year,
                price = excluded.price,
                template_mode = excluded.template_mode,
                status = excluded.status,
                storage_location = excluded.storage_location,
                data_json = excluded.data_json,
                updated_at = CURRENT_TIMESTAMP;
        """
        self.uow.execute(
            sql,
            (
                book.article,
                book.title,
                book.author,
                book.year,
                book.price,
                book.template_mode.value,
                book.status,
                book.storage_location,
                data_json,
            ),
        )

    def delete(self, article: str) -> bool:
        """Delete book and cascade to workspace tabs and outbox."""
        cursor = self.uow.execute("DELETE FROM books WHERE article = ? COLLATE NOCASE;", (article,))
        return cursor.rowcount > 0

    def search_fts(self, query: str, limit: int = 50, offset: int = 0) -> List[Book]:
        """Search books via FTS5 full-text index with support for prefixes and tokens."""
        q = (query or "").strip()
        if not q:
            cursor = self.uow.execute(
                "SELECT article, title, author, year, price, template_mode, status, "
                "storage_location, data_json, created_at, updated_at "
                "FROM books ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                (limit, offset),
            )
        else:
            # Tokenize and escape tokens for FTS5 (especially hyphens like DP-B-10005)
            tokens = re.findall(r"[\w\-]+", q)
            fts_query_parts = []
            for tok in tokens:
                if "-" in tok:
                    fts_query_parts.append(f'"{tok}"')
                else:
                    fts_query_parts.append(f"{tok}*")
            fts_expr = " ".join(fts_query_parts) if fts_query_parts else f'"{q}"'

            sql = """
                SELECT b.article, b.title, b.author, b.year, b.price, b.template_mode,
                       b.status, b.storage_location, b.data_json, b.created_at, b.updated_at
                FROM books_fts f
                JOIN books b ON b.article = f.article
                WHERE books_fts MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?;
            """
            cursor = self.uow.execute(sql, (fts_expr, limit, offset))

        books = []
        for row in cursor.fetchall():
            data = json.loads(row["data_json"] or "{}")
            data["article"] = row["article"]
            data["title"] = row["title"]
            data["author"] = row["author"]
            data["year"] = row["year"]
            data["price"] = row["price"]
            data["template_mode"] = row["template_mode"]
            data["status"] = row["status"]
            data["storage_location"] = row["storage_location"]
            data["created_at"] = str(row["created_at"])
            data["updated_at"] = str(row["updated_at"])
            books.append(Book.from_dict(data))
        return books

    def get_next_article(self, prefix: str = "DP-B-") -> str:
        """Atomically allocate the next sequential article number (no 10000 ceiling!)."""
        seq_name = "article_dp_b"
        sql = """
            UPDATE sequences
            SET next_val = next_val + 1
            WHERE name = ?
            RETURNING next_val - 1;
        """
        cursor = self.uow.execute(sql, (seq_name,))
        row = cursor.fetchone()
        if not row:
            # Seed fallback if sequences row missing
            self.uow.execute("INSERT OR IGNORE INTO sequences (name, next_val) VALUES (?, 1);", (seq_name,))
            cursor = self.uow.execute(sql, (seq_name,))
            row = cursor.fetchone()

        allocated_num = row[0]
        return f"{prefix}{allocated_num:05d}"

    def list_tabs(self) -> List[WorkspaceTab]:
        """List active workspace tabs in order."""
        cursor = self.uow.execute(
            "SELECT id, book_article, tab_order, is_active, is_edit_mode, created_at "
            "FROM workspace_tabs ORDER BY tab_order ASC;"
        )
        tabs = []
        for row in cursor.fetchall():
            tabs.append(
                WorkspaceTab(
                    id=row["id"],
                    book_article=row["book_article"],
                    tab_order=int(row["tab_order"]),
                    is_active=bool(row["is_active"]),
                    is_edit_mode=bool(row["is_edit_mode"]),
                    created_at=str(row["created_at"]),
                )
            )
        return tabs

    def save_tab(self, tab: WorkspaceTab) -> None:
        """Persist or update workspace tab."""
        sql = """
            INSERT INTO workspace_tabs (id, book_article, tab_order, is_active, is_edit_mode)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                book_article = excluded.book_article,
                tab_order = excluded.tab_order,
                is_active = excluded.is_active,
                is_edit_mode = excluded.is_edit_mode;
        """
        self.uow.execute(
            sql,
            (
                tab.id,
                tab.book_article,
                tab.tab_order,
                1 if tab.is_active else 0,
                1 if tab.is_edit_mode else 0,
            ),
        )

    def delete_tab(self, tab_id: str) -> bool:
        """Delete workspace tab."""
        cursor = self.uow.execute("DELETE FROM workspace_tabs WHERE id = ?;", (tab_id,))
        return cursor.rowcount > 0

