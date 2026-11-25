"""Background Marketplace Outbox Worker with exponential backoff and moderation polling.

Architectural Guarantees:
- Polling transactional marketplace_outbox table via SqliteUnitOfWork.
- Idempotent and thread-safe batch processing.
- Handles asynchronous Ozon task_id moderation polling.
- Exponential backoff with configurable max attempts.
- Dispatches SSE event notifications on status transitions.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.application.jobs.sse_broker import EVENT_OZON_STATUS
from backend.channels.base import IMarketplaceChannel
from backend.domain.enums import OzonSyncStatus
from backend.domain.models import OutboxItem
from backend.domain.ports import IBookRepository, IEventBroker
from backend.infrastructure.persistence.sqlite_uow import SqliteUnitOfWork

logger = logging.getLogger(__name__)


class OzonOutboxWorker:
    """Processes marketplace outbox items and monitors asynchronous Ozon import tasks."""

    def __init__(
        self,
        uow: SqliteUnitOfWork,
        book_repo: IBookRepository,
        channel: IMarketplaceChannel,
        event_broker: Optional[IEventBroker] = None,
        poll_interval: float = 2.0,
        max_attempts: int = 5,
        backoff_base_seconds: float = 2.0,
    ) -> None:
        self.uow = uow
        self.book_repo = book_repo
        self.channel = channel
        self.event_broker = event_broker
        self.poll_interval = poll_interval
        self.max_attempts = max_attempts
        self.backoff_base_seconds = backoff_base_seconds

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def enqueue(
        self,
        book_article: str,
        action: str = "publish_or_update",
    ) -> int:
        """Enqueue a new task into marketplace_outbox."""
        sql = """
            INSERT INTO marketplace_outbox (
                channel, book_article, action, status, attempts,
                next_retry_at, created_at, updated_at
            ) VALUES ('ozon', ?, ?, 'QUEUED', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        with self.uow:
            cursor = self.uow.execute(sql, (book_article, action))
            item_id = cursor.lastrowid
            assert item_id is not None
            logger.info("Enqueued outbox task %d for %s (%s)", item_id, book_article, action)
            return int(item_id)

    def process_next_batch(self, batch_size: int = 10) -> int:
        """Process up to batch_size ready outbox items."""
        with self.uow:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            query = """
                SELECT id, channel, book_article, action, status,
                       external_task_id, attempts, next_retry_at,
                       last_error, error_fields, created_at, updated_at
                FROM marketplace_outbox
                WHERE (status = 'QUEUED' AND (next_retry_at IS NULL OR next_retry_at <= ?))
                   OR (status = 'MODERATION' AND external_task_id IS NOT NULL)
                ORDER BY id ASC
                LIMIT ?;
            """
            cursor = self.uow.execute(query, (now_str, batch_size))
            rows = cursor.fetchall()
            if not rows:
                return 0

            processed = 0
            for row in rows:
                item = self._row_to_item(row)
                try:
                    if item.status == OzonSyncStatus.QUEUED:
                        self._process_queued_item(item)
                    elif item.status == OzonSyncStatus.MODERATION:
                        self._process_moderation_item(item)
                    processed += 1
                except Exception as e:
                    logger.exception("Unexpected error processing outbox item %s: %s", item.id, e)
                    self._handle_failure(item, str(e))
                    processed += 1

            return processed

    def _process_queued_item(self, item: OutboxItem) -> None:
        """Execute channel publish/update and advance to MODERATION or complete."""
        assert item.id is not None
        book = self.book_repo.get_by_article(item.book_article)
        if not book:
            self._update_item_status(
                item.id,
                OzonSyncStatus.ERROR,
                last_error=f"Book with article {item.book_article} not found",
            )
            return

        # Mark SENDING
        self._update_item_status(item.id, OzonSyncStatus.SENDING)

        try:
            res = self.channel.publish_or_update(book)
            task_id = self._extract_task_id(res)

            if task_id:
                # Ozon accepted async task -> MODERATION
                self._update_item_status(
                    item.id,
                    OzonSyncStatus.MODERATION,
                    external_task_id=str(task_id),
                    attempts=item.attempts + 1,
                )
                self._update_book_status(book.article, OzonSyncStatus.MODERATION)
            else:
                # Synchronous success without task_id
                self._update_item_status(
                    item.id,
                    OzonSyncStatus.PUBLISHED,
                    attempts=item.attempts + 1,
                )
                self._update_book_status(book.article, OzonSyncStatus.PUBLISHED)

        except Exception as exc:
            logger.warning("Channel operation failed for outbox %d: %s", item.id, exc)
            self._handle_failure(item, str(exc))

    def _process_moderation_item(self, item: OutboxItem) -> None:
        """Poll task status for items in MODERATION state."""
        assert item.id is not None
        if not item.external_task_id:
            return

        try:
            task_info = self.channel.check_status(int(item.external_task_id))
            status_str, error_msg, err_fields = self._parse_ozon_task_info(task_info)

            if status_str in ("imported", "success", "published"):
                self._update_item_status(item.id, OzonSyncStatus.PUBLISHED)
                self._update_book_status(item.book_article, OzonSyncStatus.PUBLISHED)
            elif status_str in ("failed", "rejected", "error"):
                self._update_item_status(
                    item.id,
                    OzonSyncStatus.ERROR,
                    last_error=error_msg,
                    error_fields=err_fields,
                )
                self._update_book_status(
                    item.book_article,
                    OzonSyncStatus.ERROR,
                    last_error=error_msg,
                )
            else:
                # Still in progress in Ozon (pending/processing)
                logger.debug(
                    "Outbox item %d (task %s) still in moderation: %s",
                    item.id,
                    item.external_task_id,
                    status_str,
                )
        except Exception as exc:
            logger.warning("Error checking moderation for outbox %d: %s", item.id, exc)

    def _handle_failure(self, item: OutboxItem, error_message: str) -> None:
        """Apply exponential backoff or mark final ERROR."""
        assert item.id is not None
        attempts = item.attempts + 1
        if attempts >= self.max_attempts:
            self._update_item_status(
                item.id,
                OzonSyncStatus.ERROR,
                attempts=attempts,
                last_error=error_message,
            )
            self._update_book_status(
                item.book_article,
                OzonSyncStatus.ERROR,
                last_error=error_message,
            )
        else:
            delay = self.backoff_base_seconds * (2 ** (attempts - 1))
            next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay)
            next_str = next_retry.strftime("%Y-%m-%d %H:%M:%S")

            self._update_item_status(
                item.id,
                OzonSyncStatus.QUEUED,
                attempts=attempts,
                next_retry_at=next_str,
                last_error=error_message,
            )

    def _extract_task_id(self, res: Dict[str, Any]) -> Optional[int]:
        """Safely extract task_id from diverse Ozon API responses."""
        if not isinstance(res, dict):
            return None
        # Could be directly {"result": {"task_id": 123}} or {"task_id": 123}
        if "task_id" in res:
            try:
                return int(res["task_id"])
            except (ValueError, TypeError):
                pass
        result = res.get("result")
        if isinstance(result, dict) and "task_id" in result:
            try:
                return int(result["task_id"])
            except (ValueError, TypeError):
                pass
        return None

    def _parse_ozon_task_info(
        self, task_info: Dict[str, Any]
    ) -> tuple[str, str, List[str]]:
        """Parse status, error message, and error fields from /v1/product/import/info response."""
        result = task_info.get("result", {})
        items = result.get("items", [])
        if not items:
            return "processing", "", []

        item = items[0]
        status = str(item.get("status", "processing")).lower()
        errors = item.get("errors", [])
        err_msg = ""
        err_fields: List[str] = []

        if errors:
            messages = []
            for err in errors:
                field_name = err.get("field", "")
                if field_name:
                    err_fields.append(field_name)
                messages.append(err.get("message", "Unknown Ozon error"))
            err_msg = "; ".join(messages)

        return status, err_msg, err_fields

    def _update_item_status(
        self,
        item_id: int,
        status: OzonSyncStatus,
        external_task_id: Optional[str] = None,
        attempts: Optional[int] = None,
        next_retry_at: Optional[str] = None,
        last_error: Optional[str] = None,
        error_fields: Optional[List[str]] = None,
    ) -> None:
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: List[Any] = [status.value]

        if external_task_id is not None:
            updates.append("external_task_id = ?")
            params.append(external_task_id)
        if attempts is not None:
            updates.append("attempts = ?")
            params.append(attempts)
        if next_retry_at is not None:
            updates.append("next_retry_at = ?")
            params.append(next_retry_at)
        if last_error is not None:
            updates.append("last_error = ?")
            params.append(last_error)
        if error_fields is not None:
            updates.append("error_fields = ?")
            params.append(json.dumps(error_fields, ensure_ascii=False))

        params.append(item_id)
        sql = f"UPDATE marketplace_outbox SET {', '.join(updates)} WHERE id = ?;"
        self.uow.execute(sql, tuple(params))

    def _update_book_status(
        self,
        article: str,
        status: OzonSyncStatus,
        last_error: str = "",
    ) -> None:
        if self.event_broker:
            self.event_broker.publish(
                EVENT_OZON_STATUS,
                {
                    "article": article,
                    "status": status.value,
                    "error": last_error,
                },
            )

    def _row_to_item(self, row: Any) -> OutboxItem:
        return OutboxItem(
            id=row["id"],
            channel=row["channel"],
            book_article=row["book_article"],
            action=row["action"],
            status=OzonSyncStatus(row["status"]),
            external_task_id=row["external_task_id"],
            attempts=row["attempts"],
            next_retry_at=str(row["next_retry_at"]) if row["next_retry_at"] else None,
            last_error=row["last_error"] or "",
            error_fields=json.loads(row["error_fields"] or "[]"),
            created_at=str(row["created_at"]) if row["created_at"] else None,
            updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        )

    def start(self) -> None:
        """Start the background polling loop."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="ozon-outbox-worker",
            )
            self._thread.start()
            logger.info("OzonOutboxWorker thread started.")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.process_next_batch()
            except Exception as e:
                logger.error("Error in outbox worker loop: %s", e)
            self._stop_event.wait(self.poll_interval)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background polling loop safely."""
        with self._lock:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=timeout)
                self._thread = None
                logger.info("OzonOutboxWorker thread stopped.")
