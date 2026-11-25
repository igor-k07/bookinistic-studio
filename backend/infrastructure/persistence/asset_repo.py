"""SQLite implementation of AssetRepository with Optimistic Locking.

Implements ADR-9 (Drafts & Assets in SQLite with version locking).
"""

from __future__ import annotations

import json
from typing import List, Optional

from backend.domain.exceptions import ConcurrencyError
from backend.domain.models import Asset
from backend.domain.ports import IAssetRepository
from backend.infrastructure.persistence.sqlite_uow import SqliteUnitOfWork


class SqliteAssetRepository(IAssetRepository):
    """SQLite repository for media assets with Optimistic Locking."""

    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self.uow = uow

    def get_by_id(self, asset_id: str) -> Optional[Asset]:
        """Fetch asset by ID."""
        sql = """
            SELECT id, book_article, slot, slot_order, status, status_message,
                   original_path, preview_path, ai_white_path, transformations,
                   render_hash, s3_staging_url, s3_final_url, s3_uploaded_hash,
                   version, width, height, file_size_bytes, created_at, updated_at
            FROM assets WHERE id = ?;
        """
        cursor = self.uow.execute(sql, (asset_id,))
        row = cursor.fetchone()
        if not row:
            return None

        d = dict(row)
        d["transformations"] = json.loads(d["transformations"] or "{}")
        d["created_at"] = str(d["created_at"]) if d["created_at"] else None
        d["updated_at"] = str(d["updated_at"]) if d["updated_at"] else None
        return Asset.from_dict(d)

    def save(self, asset: Asset) -> None:
        """Save asset: performs insert if new, or update with Optimistic Locking.

        Raises:
            ConcurrencyError: If asset was updated concurrently (version mismatch).
        """
        trans_json = json.dumps(asset.transformations, ensure_ascii=False)

        # Check if asset already exists
        cursor = self.uow.execute("SELECT version FROM assets WHERE id = ?;", (asset.id,))
        existing = cursor.fetchone()

        if not existing:
            # New asset insert
            sql = """
                INSERT INTO assets (
                    id, book_article, slot, slot_order, status, status_message,
                    original_path, preview_path, ai_white_path, transformations,
                    render_hash, s3_staging_url, s3_final_url, s3_uploaded_hash,
                    version, width, height, file_size_bytes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
            """
            self.uow.execute(
                sql,
                (
                    asset.id,
                    asset.book_article,
                    asset.slot,
                    asset.slot_order,
                    asset.status.value,
                    asset.status_message,
                    asset.original_path,
                    asset.preview_path,
                    asset.ai_white_path,
                    trans_json,
                    asset.render_hash,
                    asset.s3_staging_url,
                    asset.s3_final_url,
                    asset.s3_uploaded_hash,
                    asset.version,
                    asset.width,
                    asset.height,
                    asset.file_size_bytes,
                ),
            )
        else:
            # Update with Optimistic Locking
            sql = """
                UPDATE assets SET
                    book_article = ?,
                    slot = ?,
                    slot_order = ?,
                    status = ?,
                    status_message = ?,
                    original_path = ?,
                    preview_path = ?,
                    ai_white_path = ?,
                    transformations = ?,
                    render_hash = ?,
                    s3_staging_url = ?,
                    s3_final_url = ?,
                    s3_uploaded_hash = ?,
                    width = ?,
                    height = ?,
                    file_size_bytes = ?,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND version = ?;
            """
            cursor = self.uow.execute(
                sql,
                (
                    asset.book_article,
                    asset.slot,
                    asset.slot_order,
                    asset.status.value,
                    asset.status_message,
                    asset.original_path,
                    asset.preview_path,
                    asset.ai_white_path,
                    trans_json,
                    asset.render_hash,
                    asset.s3_staging_url,
                    asset.s3_final_url,
                    asset.s3_uploaded_hash,
                    asset.width,
                    asset.height,
                    asset.file_size_bytes,
                    asset.id,
                    asset.version,
                ),
            )
            if cursor.rowcount == 0:
                raise ConcurrencyError(
                    f"Optimistic lock conflict on asset '{asset.id}': expected version {asset.version}"
                )
            asset.version += 1

    def list_by_article(self, article: str) -> List[Asset]:
        """List all assets assigned to a book ordered by slot_order."""
        sql = """
            SELECT id, book_article, slot, slot_order, status, status_message,
                   original_path, preview_path, ai_white_path, transformations,
                   render_hash, s3_staging_url, s3_final_url, s3_uploaded_hash,
                   version, width, height, file_size_bytes, created_at, updated_at
            FROM assets WHERE book_article = ? COLLATE NOCASE
            ORDER BY slot_order ASC;
        """
        cursor = self.uow.execute(sql, (article,))
        assets = []
        for row in cursor.fetchall():
            d = dict(row)
            d["transformations"] = json.loads(d["transformations"] or "{}")
            d["created_at"] = str(d["created_at"]) if d["created_at"] else None
            d["updated_at"] = str(d["updated_at"]) if d["updated_at"] else None
            assets.append(Asset.from_dict(d))
        return assets

    def delete(self, asset_id: str) -> bool:
        """Delete asset record."""
        cursor = self.uow.execute("DELETE FROM assets WHERE id = ?;", (asset_id,))
        return cursor.rowcount > 0
