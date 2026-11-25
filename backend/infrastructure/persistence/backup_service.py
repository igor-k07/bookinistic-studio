"""Store-scoped SQLite cloud backup and WAL-safe restore service.

Implements ADR-6 (Two-tier backup isolation) and WAL checkpoint integrity.
"""

from __future__ import annotations

import logging
import sqlite3
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BackupService:
    """Service for consistent SQLite snapshots, S3 cloud synchronization, and WAL-safe restore."""

    def __init__(self) -> None:
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def create_local_snapshot(self, src_db_path: Path, dst_snapshot_path: Path) -> None:
        """Create a consistent SQLite snapshot via sqlite3.backup() without blocking live WAL."""
        src_conn = sqlite3.connect(str(src_db_path), timeout=30.0)
        dst_conn = sqlite3.connect(str(dst_snapshot_path), timeout=30.0)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()

    def verify_integrity(self, db_path: Path) -> bool:
        """Run PRAGMA integrity_check on a database file."""
        try:
            conn = sqlite3.connect(str(db_path), timeout=30.0)
            try:
                cursor = conn.execute("PRAGMA integrity_check;")
                res = cursor.fetchone()
                return bool(res and res[0] == "ok")
            finally:
                conn.close()
        except (sqlite3.DatabaseError, OSError):
            return False

    def backup_to_s3(
        self,
        store_id: str,
        db_path: Path,
        s3_client: Any,
        bucket: str,
    ) -> Dict[str, Any]:
        """Create a store-isolated atomic snapshot and upload to Yandex S3."""
        if not db_path.is_file():
            raise FileNotFoundError(f"Database file not found: {db_path}")

        # Create temporary snapshot
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            self.create_local_snapshot(db_path, tmp_path)
            if not self.verify_integrity(tmp_path):
                raise RuntimeError(f"Integrity check failed for snapshot of {db_path}")

            size_bytes = tmp_path.stat().st_size
            today_str = datetime.now().strftime("%Y-%m-%d")

            # Store-scoped S3 keys
            latest_key = f"backups/db/{store_id}/catalog_latest.db"
            history_key = f"backups/db/{store_id}/history/catalog_{today_str}.db"

            # Upload latest copy
            with tmp_path.open("rb") as f:
                s3_client.put_object(
                    Bucket=bucket,
                    Key=latest_key,
                    Body=f,
                    ContentType="application/x-sqlite3",
                )

            # Upload daily historical copy
            with tmp_path.open("rb") as f:
                s3_client.put_object(
                    Bucket=bucket,
                    Key=history_key,
                    Body=f,
                    ContentType="application/x-sqlite3",
                )

            logger.info(f"Store '{store_id}' DB backed up to {latest_key} ({size_bytes} bytes).")
            return {
                "success": True,
                "store_id": store_id,
                "latest_key": latest_key,
                "history_key": history_key,
                "size_bytes": size_bytes,
            }
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def restore_from_s3(
        self,
        store_id: str,
        target_db_path: Path,
        s3_client: Any,
        bucket: str,
        s3_key: Optional[str] = None,
    ) -> bool:
        """Download store backup, verify integrity, clean WAL/SHM, and swap atomically."""
        key = s3_key or f"backups/db/{store_id}/catalog_latest.db"
        target_db_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            dir=target_db_path.parent, suffix=".restore.tmp", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)

        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            body = response["Body"].read()
            tmp_path.write_bytes(body)

            # Verify integrity before replacing active database
            if not self.verify_integrity(tmp_path):
                raise ValueError(f"Integrity check failed on downloaded backup: {key}")

            # WAL-safe cleanup: remove existing WAL and SHM files
            wal_file = target_db_path.with_name(f"{target_db_path.name}-wal")
            shm_file = target_db_path.with_name(f"{target_db_path.name}-shm")
            if wal_file.exists():
                wal_file.unlink()
            if shm_file.exists():
                shm_file.unlink()

            # Atomic swap
            tmp_path.replace(target_db_path)

            # Ensure restored DB is in WAL mode
            conn = sqlite3.connect(str(target_db_path))
            try:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
            finally:
                conn.close()

            logger.info(f"Store '{store_id}' restored successfully from {key}.")
            return True
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def backup_async(
        self,
        store_id: str,
        db_path: Path,
        s3_client: Any,
        bucket: str,
        delay: float = 2.0,
    ) -> None:
        """Debounced asynchronous backup for a specific store."""
        with self._lock:
            if store_id in self._timers:
                self._timers[store_id].cancel()

            def _run() -> None:
                try:
                    self.backup_to_s3(store_id, db_path, s3_client, bucket)
                except Exception as e:
                    logger.error(f"Async backup failed for store '{store_id}': {e}")
                finally:
                    with self._lock:
                        self._timers.pop(store_id, None)

            timer = threading.Timer(delay, _run)
            timer.daemon = True
            self._timers[store_id] = timer
            timer.start()
