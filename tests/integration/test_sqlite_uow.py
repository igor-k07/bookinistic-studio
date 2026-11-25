"""Integration tests for SqliteUnitOfWork and migrations (Step 2.1)."""

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from backend.infrastructure.persistence.sqlite_uow import (
    SqliteUnitOfWork,
    run_migrations,
)


def _get_open_fd_count() -> int:
    """Return count of currently open file descriptors on POSIX/macOS."""
    try:
        return len(os.listdir("/dev/fd"))
    except OSError:
        return 0


def test_no_fd_leak_after_500_queries(tmp_path: Path) -> None:
    """Verify that SqliteUnitOfWork cleanly closes connections in finally with no FD leak."""
    db_file = tmp_path / "leak_test.db"
    run_migrations(db_file)

    # Warmup
    with SqliteUnitOfWork(db_file) as uow:
        uow.execute("SELECT 1;")

    initial_fds = _get_open_fd_count()

    for i in range(500):
        with SqliteUnitOfWork(db_file) as uow:
            cursor = uow.execute("SELECT ?", (i,))
            val = cursor.fetchone()[0]
            assert val == i

    final_fds = _get_open_fd_count()
    # FD count should not leak 500 descriptors
    if initial_fds > 0:
        assert abs(final_fds - initial_fds) <= 5, f"FD leak detected: {initial_fds} -> {final_fds}"


def test_transaction_rollback_on_error(tmp_path: Path) -> None:
    """Verify transaction rolls back cleanly on exception."""
    db_file = tmp_path / "rollback_test.db"
    run_migrations(db_file)

    with pytest.raises(RuntimeError, match="Simulated failure"):
        with SqliteUnitOfWork(db_file) as uow:
            uow.begin()
            uow.execute(
                "INSERT INTO books (article, title) VALUES (?, ?);",
                ("DP-B-9999", "Тестовая книга"),
            )
            raise RuntimeError("Simulated failure")

    # Verify book was NOT persisted
    with SqliteUnitOfWork(db_file) as uow:
        cursor = uow.execute("SELECT COUNT(*) FROM books WHERE article = 'DP-B-9999';")
        assert cursor.fetchone()[0] == 0


def test_migration_on_copy_of_real_db(tmp_path: Path) -> None:
    """Test non-destructive migration on a real catalog.db copy."""
    real_db = Path("storage/catalog.db")
    if not real_db.is_file():
        pytest.skip("storage/catalog.db not found for real DB test")

    tmp_db = tmp_path / "catalog_copy.db"
    shutil.copy2(real_db, tmp_db)

    # Pre-migration count
    raw_conn = sqlite3.connect(tmp_db)
    raw_count = raw_conn.execute("SELECT COUNT(*) FROM books;").fetchone()[0]
    raw_conn.close()

    assert raw_count > 0, "Real DB must contain books"

    # Run migration
    run_migrations(tmp_db)

    with SqliteUnitOfWork(tmp_db) as uow:
        # 1. user_version must be 1
        ver = uow.execute("PRAGMA user_version;").fetchone()[0]
        assert ver == 1

        # 2. Book count must be completely preserved
        post_count = uow.execute("SELECT COUNT(*) FROM books;").fetchone()[0]
        assert post_count == raw_count

        # 3. FTS5 table must be populated and searchable
        fts_count = uow.execute("SELECT COUNT(*) FROM books_fts;").fetchone()[0]
        assert fts_count == raw_count

        sample_book = uow.execute("SELECT article, title FROM books LIMIT 1;").fetchone()
        art = sample_book["article"]
        # FTS5 requires quotes around tokens with hyphens
        quoted_art = f'"{art}"'
        fts_search = uow.execute("SELECT article FROM books_fts WHERE books_fts MATCH ?;", (quoted_art,)).fetchall()
        assert len(fts_search) >= 1

        # 4. Sequences must have allocated next value > max existing article
        seq_val = uow.execute("SELECT next_val FROM sequences WHERE name = 'article_dp_b';").fetchone()[0]
        assert seq_val > 1000

        # 5. Reference brands must be populated
        brands_count = uow.execute("SELECT COUNT(*) FROM reference_brands;").fetchone()[0]
        assert brands_count >= 30

    # Test idempotency: running migrations again does not alter anything
    run_migrations(tmp_db)
    with SqliteUnitOfWork(tmp_db) as uow:
        ver = uow.execute("PRAGMA user_version;").fetchone()[0]
        assert ver == 1
        post_count_2 = uow.execute("SELECT COUNT(*) FROM books;").fetchone()[0]
        assert post_count_2 == raw_count
