"""Integration tests for store-scoped cloud backup and WAL-safe restore (Step 2.3)."""

import io
from pathlib import Path
from typing import Any, Dict

import pytest

from backend.domain.models import Book
from backend.infrastructure.persistence.backup_service import BackupService
from backend.infrastructure.persistence.book_repo import SqliteBookRepository
from backend.infrastructure.persistence.sqlite_uow import (
    SqliteUnitOfWork,
    run_migrations,
)


class MockS3Client:
    """In-memory mock for boto3 S3 client."""

    def __init__(self) -> None:
        self.objects: Dict[str, bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: Any, ContentType: str = "") -> None:
        if hasattr(Body, "read"):
            data = Body.read()
        else:
            data = Body
        self.objects[f"{Bucket}/{Key}"] = data

    def get_object(self, Bucket: str, Key: str) -> Dict[str, Any]:
        full_key = f"{Bucket}/{Key}"
        if full_key not in self.objects:
            raise KeyError(f"NoSuchKey: {Key}")
        return {"Body": io.BytesIO(self.objects[full_key])}


def test_store_isolated_backup_and_restore(tmp_path: Path) -> None:
    """Verify backups for store 870997 and 2727930 are strictly isolated in S3."""
    backup_service = BackupService()
    s3_client = MockS3Client()
    bucket = "test-bookinistic-bucket"

    db_870 = tmp_path / "stores" / "870997" / "catalog.db"
    db_272 = tmp_path / "stores" / "2727930" / "catalog.db"

    run_migrations(db_870)
    run_migrations(db_272)

    # Insert distinct books into each store
    with SqliteUnitOfWork(db_870) as uow:
        repo = SqliteBookRepository(uow)
        repo.save(Book(article="DP-B-08701", title="Книга Магазина 870997"))

    with SqliteUnitOfWork(db_272) as uow:
        repo = SqliteBookRepository(uow)
        repo.save(Book(article="DP-B-02701", title="Книга Магазина 2727930"))

    # Perform backups for both stores
    res_870 = backup_service.backup_to_s3("870997", db_870, s3_client, bucket)
    res_272 = backup_service.backup_to_s3("2727930", db_272, s3_client, bucket)

    # 1. Verify isolated S3 keys
    assert res_870["latest_key"] == "backups/db/870997/catalog_latest.db"
    assert res_272["latest_key"] == "backups/db/2727930/catalog_latest.db"
    assert res_870["latest_key"] != res_272["latest_key"]

    key_870 = f"{bucket}/{res_870['latest_key']}"
    key_272 = f"{bucket}/{res_272['latest_key']}"
    assert key_870 in s3_client.objects
    assert key_272 in s3_client.objects
    assert s3_client.objects[key_870] != s3_client.objects[key_272]

    # 2. Simulate local disaster: delete local DB and add dirty lingering WAL/SHM
    db_870.unlink()
    wal_file = db_870.with_name(f"{db_870.name}-wal")
    shm_file = db_870.with_name(f"{db_870.name}-shm")
    wal_file.write_text("corrupted_wal_residue")
    shm_file.write_text("corrupted_shm_residue")

    # 3. Restore store 870997 from S3
    restored = backup_service.restore_from_s3("870997", db_870, s3_client, bucket)
    assert restored
    assert db_870.is_file()
    assert not wal_file.exists(), "Old WAL file must be cleaned up on restore"
    assert not shm_file.exists(), "Old SHM file must be cleaned up on restore"

    # 4. Verify data integrity and store isolation after restore
    assert backup_service.verify_integrity(db_870)

    with SqliteUnitOfWork(db_870) as uow:
        repo = SqliteBookRepository(uow)
        book_870 = repo.get_by_article("DP-B-08701")
        assert book_870 is not None
        assert book_870.title == "Книга Магазина 870997"

        # Verify that store 2727930 book is NOT in store 870997
        assert repo.get_by_article("DP-B-02701") is None


def test_corrupted_backup_rejected_on_restore(tmp_path: Path) -> None:
    """Verify that corrupt backup payloads are rejected and never overwrite active DB."""
    backup_service = BackupService()
    s3_client = MockS3Client()
    bucket = "test-bucket"
    store_id = "test_store"

    target_db = tmp_path / "valid.db"
    run_migrations(target_db)
    with SqliteUnitOfWork(target_db) as uow:
        SqliteBookRepository(uow).save(Book(article="DP-B-00001", title="Оригинальная книга"))

    # Upload corrupt garbage to S3
    corrupt_key = f"backups/db/{store_id}/catalog_latest.db"
    s3_client.put_object(bucket, corrupt_key, b"THIS_IS_NOT_A_SQLITE_DATABASE_CORRUPT")

    # Attempt restore
    with pytest.raises(ValueError, match="Integrity check failed"):
        backup_service.restore_from_s3(store_id, target_db, s3_client, bucket)

    # Active DB must be completely unharmed
    with SqliteUnitOfWork(target_db) as uow:
        book = SqliteBookRepository(uow).get_by_article("DP-B-00001")
        assert book is not None
        assert book.title == "Оригинальная книга"
