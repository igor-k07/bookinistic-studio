"""Persistence infrastructure layer for Bookinistic Studio 2.0."""

from backend.infrastructure.persistence.asset_repo import SqliteAssetRepository
from backend.infrastructure.persistence.backup_service import BackupService
from backend.infrastructure.persistence.book_repo import SqliteBookRepository
from backend.infrastructure.persistence.reference_repo import SqliteReferenceRepository
from backend.infrastructure.persistence.sqlite_uow import (
    SqliteUnitOfWork,
    run_migrations,
)

__all__ = [
    "BackupService",
    "SqliteAssetRepository",
    "SqliteBookRepository",
    "SqliteReferenceRepository",
    "SqliteUnitOfWork",
    "run_migrations",
]
