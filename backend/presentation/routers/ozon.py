"""Ozon marketplace integration, profiles, outbox, and smart-sync router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.presentation.dto import SwitchProfileRequest, SyncSmartS3Request

router = APIRouter(prefix="/api/ozon", tags=["Ozon Marketplace"])


@router.get("/status")
def get_ozon_status(request: Request) -> Any:
    """Return status of outbox queue, background sync worker, and channel connectivity."""
    app_state = request.app.state
    registry = app_state.store_registry
    ctx = registry.get_active_context()

    with ctx.uow:
        cursor = ctx.uow.execute(
            "SELECT status, COUNT(*) as count FROM marketplace_outbox GROUP BY status;"
        )
        counts = {row["status"]: row["count"] for row in cursor.fetchall()}

    return {
        "active_store": registry.active_store_id,
        "outbox_counts": counts,
        "is_configured": bool(getattr(ctx.ozon_gateway, "is_configured", False))
        if hasattr(ctx, "ozon_gateway")
        else False,
    }


@router.post("/switch-profile")
def switch_store_profile(req: SwitchProfileRequest, request: Request) -> Any:
    """Switch the active store profile in StoreRegistry and re-wire store components."""
    registry = request.app.state.store_registry
    try:
        registry.set_active_store(req.store_id)
        from backend.main import init_store_components

        cfg = getattr(request.app.state, "settings", None)
        if cfg is not None:
            if hasattr(request.app.state, "outbox_worker") and request.app.state.outbox_worker:
                request.app.state.outbox_worker.stop()
            init_store_components(registry, request.app, cfg)
            if hasattr(request.app.state, "outbox_worker") and request.app.state.outbox_worker:
                request.app.state.outbox_worker.start()

        if hasattr(request.app.state, "event_broker") and request.app.state.event_broker:
            request.app.state.event_broker.publish(
                "store.switched",
                {"active_store": req.store_id},
            )
        return {"status": "ok", "active_store": req.store_id}
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/retry/{article}")
def retry_outbox_article(article: str, request: Request) -> Any:
    """Reset outbox item attempts and retry immediate submission."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        cursor = ctx.uow.execute(
            """
            UPDATE marketplace_outbox
            SET status = 'QUEUED', attempts = 0, next_retry_at = CURRENT_TIMESTAMP, last_error = ''
            WHERE book_article = ? COLLATE NOCASE;
            """,
            (article,),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"No outbox task found for {article}")
    return {"status": "re-queued", "article": article}


@router.post("/import")
def run_outbox_batch(request: Request) -> Any:
    """Trigger immediate processing of the marketplace outbox queue."""
    app_state = request.app.state
    if hasattr(app_state, "outbox_worker") and app_state.outbox_worker:
        processed = app_state.outbox_worker.process_next_batch(batch_size=10)
        return {"status": "ok", "processed_count": processed}
    return {"status": "no_worker", "processed_count": 0}


@router.post("/sync/smart-s3")
def trigger_smart_s3_sync(req: SyncSmartS3Request, request: Request) -> Any:
    """Trigger incremental Ozon -> S3 -> SQLite photo URL sync strictly chunked by 50."""
    use_case = request.app.state.sync_catalog_use_case
    registry = request.app.state.store_registry
    store_id = req.store_id if req.store_id and req.store_id != "default" else registry.active_store_id
    return use_case.execute(store_id=store_id, batch_size=req.batch_size)


@router.post("/update-pictures/{article}")
def update_ozon_pictures(article: str, request: Request) -> Any:
    """Targeted Ozon photo update for an existing catalog book."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        book = ctx.book_repo.get_by_article(article)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book {article} not found")
    res = ctx.ozon_channel.publish_or_update(book)
    return {"status": "ok", "article": article, "result": res}
