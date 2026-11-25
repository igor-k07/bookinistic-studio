"""Integration tests for repositories, concurrency, and optimistic locking (Step 2.2)."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.domain.enums import AssetStatus, BookEra, PhotoRole
from backend.domain.exceptions import ConcurrencyError
from backend.domain.models import Asset, Book
from backend.infrastructure.persistence.asset_repo import SqliteAssetRepository
from backend.infrastructure.persistence.book_repo import SqliteBookRepository
from backend.infrastructure.persistence.reference_repo import SqliteReferenceRepository
from backend.infrastructure.persistence.sqlite_uow import (
    SqliteUnitOfWork,
    run_migrations,
)


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "repo_test.db"
    run_migrations(db_file)
    return db_file


def test_book_repo_crud_and_fts5(test_db: Path) -> None:
    """Test BookRepository CRUD and FTS5 search."""
    with SqliteUnitOfWork(test_db) as uow:
        repo = SqliteBookRepository(uow)
        book = Book(
            article="DP-B-00100",
            title="Преступление и наказание",
            author="Фёдор Достоевский",
            year=1866,
            price=2500.0,
            template_mode=BookEra.PRE2011,
            publisher="Наука",
        )
        repo.save(book)

    # Read back
    with SqliteUnitOfWork(test_db) as uow:
        repo = SqliteBookRepository(uow)
        loaded = repo.get_by_article("DP-B-00100")
        assert loaded is not None
        assert loaded.title == "Преступление и наказание"
        assert loaded.author == "Фёдор Достоевский"
        assert loaded.publisher == "Наука"

        # FTS5 search by title word
        results = repo.search_fts("Преступление")
        assert len(results) == 1
        assert results[0].article == "DP-B-00100"

        # FTS5 search by author prefix
        results_author = repo.search_fts("Достоев")
        assert len(results_author) == 1

        # Delete
        assert repo.delete("DP-B-00100")
        assert repo.get_by_article("DP-B-00100") is None


def test_article_allocation_above_10000(test_db: Path) -> None:
    """Verify article allocation has no 10000 ceiling bug."""
    with SqliteUnitOfWork(test_db) as uow:
        uow.execute("UPDATE sequences SET next_val = 10005 WHERE name = 'article_dp_b';")

    with SqliteUnitOfWork(test_db) as uow:
        repo = SqliteBookRepository(uow)
        art1 = repo.get_next_article()
        art2 = repo.get_next_article()
        assert art1 == "DP-B-10005"
        assert art2 == "DP-B-10006"


def test_concurrent_article_allocation(test_db: Path) -> None:
    """Verify concurrent article allocations produce unique numbers without duplicates."""
    def allocate_article(idx: int) -> str:
        with SqliteUnitOfWork(test_db) as uow:
            uow.begin()
            repo = SqliteBookRepository(uow)
            art = repo.get_next_article()
            uow.commit()
            return art

    with ThreadPoolExecutor(max_workers=5) as executor:
        articles = list(executor.map(allocate_article, range(20)))

    assert len(articles) == 20
    assert len(set(articles)) == 20, "All allocated articles must be unique"


def test_asset_repo_optimistic_locking_race(test_db: Path) -> None:
    """Verify Optimistic Locking prevents lost updates and raises ConcurrencyError."""
    # Create book first to satisfy foreign key constraint
    with SqliteUnitOfWork(test_db) as uow:
        book_repo = SqliteBookRepository(uow)
        book_repo.save(Book(article="DP-B-00001", title="Книга 1"))

    asset_id = "ast_race_001"
    asset = Asset(
        id=asset_id,
        book_article="DP-B-00001",
        slot=PhotoRole.COVER_FRONT.value,
        original_path="storage/test.jpg",
        preview_path="storage/test_prev.jpg",
        status=AssetStatus.UPLOADED,
        version=1,
    )

    with SqliteUnitOfWork(test_db) as uow:
        repo = SqliteAssetRepository(uow)
        repo.save(asset)

    # Simulate two concurrent sessions loading the same asset version 1
    with SqliteUnitOfWork(test_db) as uow1:
        repo1 = SqliteAssetRepository(uow1)
        asset_user1 = repo1.get_by_id(asset_id)
        assert asset_user1 is not None
        assert asset_user1.version == 1

    with SqliteUnitOfWork(test_db) as uow2:
        repo2 = SqliteAssetRepository(uow2)
        asset_user2 = repo2.get_by_id(asset_id)
        assert asset_user2 is not None
        assert asset_user2.version == 1

    # User 1 saves changes -> succeeds, version advances to 2
    with SqliteUnitOfWork(test_db) as uow1:
        repo1 = SqliteAssetRepository(uow1)
        asset_user1.transformations = {"rotation": 90}
        repo1.save(asset_user1)
        assert asset_user1.version == 2

    # User 2 attempts to save changes with stale version 1 -> ConcurrencyError!
    with SqliteUnitOfWork(test_db) as uow2:
        repo2 = SqliteAssetRepository(uow2)
        asset_user2.transformations = {"rotation": 180}
        with pytest.raises(ConcurrencyError, match="Optimistic lock conflict"):
            repo2.save(asset_user2)


def test_reference_brands_autocomplete(test_db: Path) -> None:
    """Verify ReferenceRepository fast search and autocomplete."""
    with SqliteUnitOfWork(test_db) as uow:
        repo = SqliteReferenceRepository(uow)
        assert repo.is_known_brand("Наука")
        assert repo.is_known_brand("эксмо")  # Case-insensitive
        assert not repo.is_known_brand("НесуществующееИздательство123")

        # Prefix priority search
        results = repo.search_brands("Нау", limit=5)
        assert len(results) >= 1
        assert results[0] == "Наука"

        # Add custom brand
        repo.add_brand("Издательство МГУ")
        assert repo.is_known_brand("Издательство МГУ")
