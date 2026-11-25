"""Unit tests for SSEBroker, JobManager, and OzonOutboxWorker (Step 5.1).

Architectural Verification:
1. Thread-safe SSEBroker event pub/sub, SSE wire format, and bounded queue overflow handling.
2. JobManager CPU/IO pool execution, key-based deduplication, cancellation, and progress.
3. OzonOutboxWorker state machine: QUEUED -> SENDING -> MODERATION -> PUBLISHED/ERROR,
   exponential backoff, task_id extraction, and SSE notifications.
"""

import time
from unittest.mock import MagicMock

import pytest

from backend.application.jobs.job_manager import JobManager
from backend.application.jobs.sse_broker import (
    EVENT_ASSET_UPDATED,
    EVENT_OZON_STATUS,
    SSEBroker,
    SSEEvent,
)
from backend.channels.ozon.outbox_worker import OzonOutboxWorker
from backend.domain.enums import BookEra
from backend.domain.models import Book
from backend.infrastructure.persistence.book_repo import SqliteBookRepository
from backend.infrastructure.persistence.sqlite_uow import SqliteUnitOfWork, run_migrations

# --- 1. SSEBroker Tests ---


def test_sse_broker_publish_subscribe():
    broker = SSEBroker(max_queue_size=10)
    client_q = broker.subscribe()
    assert broker.subscriber_count == 1

    broker.publish(EVENT_ASSET_UPDATED, {"asset_id": "ast-123", "status": "READY"})

    event = client_q.get(timeout=1.0)
    assert isinstance(event, SSEEvent)
    assert event.event_type == EVENT_ASSET_UPDATED
    assert event.data["asset_id"] == "ast-123"

    wire = event.to_sse_message()
    assert "event: asset.updated" in wire
    assert '"asset_id": "ast-123"' in wire
    assert wire.endswith("\n\n")

    broker.unsubscribe(client_q)
    assert broker.subscriber_count == 0


def test_sse_broker_bounded_queue_overflow_cleanup():
    broker = SSEBroker(max_queue_size=2)
    _client_q = broker.subscribe()

    # Fill queue to capacity
    broker.publish("test.event", {"n": 1})
    broker.publish("test.event", {"n": 2})

    # 3rd event exceeds maxsize=2 -> broker should drop and discard client
    broker.publish("test.event", {"n": 3})
    assert broker.subscriber_count == 0


# --- 2. JobManager Tests ---


def test_job_manager_io_and_cpu_execution():
    broker = MagicMock()
    jm = JobManager(cpu_workers=2, io_workers=4, event_broker=broker)

    def simple_add(a: int, b: int) -> int:
        return a + b

    job_io = jm.submit(simple_add, 10, 20, pool="io")
    while not job_io.is_done:
        time.sleep(0.01)

    assert job_io.status == "completed"
    assert job_io.result == 30
    assert job_io.progress == 1.0

    job_cpu = jm.submit(simple_add, 50, 50, pool="cpu")
    while not job_cpu.is_done:
        time.sleep(0.01)

    assert job_cpu.status == "completed"
    assert job_cpu.result == 100

    jm.shutdown(wait=True)


def test_job_manager_deduplication():
    jm = JobManager(cpu_workers=1, io_workers=2)

    def slow_task():
        time.sleep(0.1)
        return "done"

    job1 = jm.submit(slow_task, job_key="unique-task-1")
    job2 = jm.submit(slow_task, job_key="unique-task-1")

    # job2 must be the exact same instance as job1
    assert job1.job_id == job2.job_id

    while not job1.is_done:
        time.sleep(0.02)

    assert job1.status == "completed"
    assert jm.get_job_by_key("unique-task-1") == job1

    jm.shutdown(wait=True)


def test_job_manager_cancellation_and_progress():
    jm = JobManager(cpu_workers=1, io_workers=1)

    def cancelable_task():
        time.sleep(0.2)
        return "finished"

    job = jm.submit(cancelable_task)
    jm.update_progress(job.job_id, 0.5, "Halfway done")

    assert job.progress == 0.5
    assert job.message == "Halfway done"

    cancelled = jm.cancel(job.job_id)
    assert cancelled is True
    assert job.cancel_requested is True

    jm.shutdown(wait=True)


def test_job_manager_handles_exception():
    jm = JobManager(cpu_workers=1, io_workers=1)

    def broken_task():
        raise ValueError("Something exploded!")

    job = jm.submit(broken_task)
    while not job.is_done:
        time.sleep(0.01)

    assert job.status == "failed"
    assert "Something exploded!" in (job.error or "")

    jm.shutdown(wait=True)


# --- 3. OzonOutboxWorker Tests ---


@pytest.fixture
def uow_and_repo(tmp_path):
    db_path = tmp_path / "test_outbox.db"
    run_migrations(db_path)
    uow = SqliteUnitOfWork(db_path)
    repo = SqliteBookRepository(uow)
    return uow, repo


@pytest.fixture
def sample_book(uow_and_repo):
    uow, repo = uow_and_repo
    book = Book(
        article="DP-B-99001",
        title="Тестовая книга Outbox",
        author="Автор Тестовый",
        year=1985,
        price=500.0,
        template_mode=BookEra.PRE2011,
    )
    with uow:
        repo.save(book)
    return book


def test_outbox_worker_publish_to_moderation_to_published(uow_and_repo, sample_book):
    uow, repo = uow_and_repo
    channel = MagicMock()
    broker = MagicMock()

    # Step 1: Channel returns an async task_id = 9988
    channel.publish_or_update.return_value = {"result": {"task_id": 9988}}

    worker = OzonOutboxWorker(
        uow=uow,
        book_repo=repo,
        channel=channel,
        event_broker=broker,
    )

    item_id = worker.enqueue(sample_book.article, "publish_or_update")
    assert item_id > 0

    # Process first batch: QUEUED -> SENDING -> MODERATION
    processed = worker.process_next_batch(batch_size=10)
    assert processed == 1

    # Verify outbox record in DB transitioned to MODERATION
    with uow:
        row = uow.execute("SELECT * FROM marketplace_outbox WHERE id = ?", (item_id,)).fetchone()
        assert row["status"] == "MODERATION"
        assert row["external_task_id"] == "9988"

    # Step 2: Moderation polling returns imported status
    channel.check_status.return_value = {
        "result": {"items": [{"status": "imported", "errors": []}]}
    }

    processed_mod = worker.process_next_batch(batch_size=10)
    assert processed_mod == 1

    with uow:
        row_final = uow.execute("SELECT * FROM marketplace_outbox WHERE id = ?", (item_id,)).fetchone()
        assert row_final["status"] == "PUBLISHED"

    # Verify SSE broker received status update
    broker.publish.assert_any_call(
        EVENT_OZON_STATUS,
        {"article": sample_book.article, "status": "PUBLISHED", "error": ""},
    )


def test_outbox_worker_moderation_error_fields(uow_and_repo, sample_book):
    uow, repo = uow_and_repo
    channel = MagicMock()
    broker = MagicMock()

    channel.publish_or_update.return_value = {"result": {"task_id": 7766}}
    worker = OzonOutboxWorker(uow=uow, book_repo=repo, channel=channel, event_broker=broker)

    item_id = worker.enqueue(sample_book.article)
    worker.process_next_batch()

    # Moderation fails with validation error on ISBN
    channel.check_status.return_value = {
        "result": {
            "items": [
                {
                    "status": "failed",
                    "errors": [{"field": "isbn", "message": "Invalid ISBN format"}],
                }
            ]
        }
    }

    worker.process_next_batch()

    with uow:
        row = uow.execute("SELECT * FROM marketplace_outbox WHERE id = ?", (item_id,)).fetchone()
        assert row["status"] == "ERROR"
        assert "Invalid ISBN format" in row["last_error"]
        assert "isbn" in row["error_fields"]


def test_outbox_worker_exponential_backoff_and_max_attempts(uow_and_repo, sample_book):
    uow, repo = uow_and_repo
    channel = MagicMock()
    channel.publish_or_update.side_effect = ConnectionError("Ozon API timeout")

    worker = OzonOutboxWorker(
        uow=uow,
        book_repo=repo,
        channel=channel,
        max_attempts=3,
        backoff_base_seconds=0.1,
    )

    item_id = worker.enqueue(sample_book.article)

    # Attempt 1 -> fails -> status set to QUEUED with next_retry_at in future
    worker.process_next_batch()
    with uow:
        row1 = uow.execute("SELECT * FROM marketplace_outbox WHERE id = ?", (item_id,)).fetchone()
        assert row1["status"] == "QUEUED"
        assert row1["attempts"] == 1
        assert "Ozon API timeout" in row1["last_error"]

        # Attempt 2 -> manually reset next_retry_at to past to simulate time passing
        uow.execute(
            "UPDATE marketplace_outbox SET next_retry_at = '2000-01-01 00:00:00' WHERE id = ?",
            (item_id,),
        )
    worker.process_next_batch()
    with uow:
        row2 = uow.execute("SELECT * FROM marketplace_outbox WHERE id = ?", (item_id,)).fetchone()
        assert row2["attempts"] == 2
        assert row2["status"] == "QUEUED"

        # Attempt 3 -> reaches max_attempts=3 -> transitions to ERROR
        uow.execute(
            "UPDATE marketplace_outbox SET next_retry_at = '2000-01-01 00:00:00' WHERE id = ?",
            (item_id,),
        )
    worker.process_next_batch()
    with uow:
        row3 = uow.execute("SELECT * FROM marketplace_outbox WHERE id = ?", (item_id,)).fetchone()
        assert row3["attempts"] == 3
        assert row3["status"] == "ERROR"
