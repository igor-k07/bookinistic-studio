"""Ozon marketplace integration, profiles, outbox, and smart-sync router."""

from __future__ import annotations

import threading
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from backend.channels.ozon.mapper import ozon_response_to_book_dict
from backend.domain.enums import OzonSyncStatus
from backend.domain.models import Book
from backend.presentation.dto import SwitchProfileRequest, SyncSmartS3Request

router = APIRouter(prefix="/api/ozon", tags=["Ozon Marketplace"])

_import_lock = threading.Lock()
_import_status: Dict[str, Any] = {
    "running": False,
    "progress": 0,
    "total": 0,
    "imported": 0,
    "updated": 0,
    "error": None,
    "done": False,
}


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


@router.get("/import-status")
def get_ozon_import_status() -> Dict[str, Any]:
    """Return live progress of background Ozon -> SQLite catalog import."""
    with _import_lock:
        return dict(_import_status)


@router.post("/import-catalog")
def start_ozon_catalog_import(request: Request) -> Dict[str, Any]:
    """Pull all product cards and attributes from Ozon Seller API into local catalog.db."""
    ctx = request.app.state.store_registry.get_active_context()
    if not ctx.ozon_gateway.is_configured:
        raise HTTPException(status_code=400, detail="Ozon API ключи не настроены для этого магазина")

    with _import_lock:
        if _import_status["running"]:
            return dict(_import_status)
        _import_status.update(
            {"running": True, "progress": 0, "total": 0, "imported": 0, "updated": 0, "error": None, "done": False}
        )

    def _worker() -> None:
        try:
            offer_ids: List[str] = []
            last_id = ""
            while True:
                resp = ctx.ozon_gateway.list_products(limit=1000, last_id=last_id)
                result = resp.get("result", {}) if isinstance(resp, dict) else {}
                items = result.get("items", []) if isinstance(result, dict) else []
                for it in items:
                    oid = str(it.get("offer_id") or "").strip()
                    if oid:
                        offer_ids.append(oid)
                next_last = str(result.get("last_id") or "")
                if not items or not next_last or next_last == last_id:
                    break
                last_id = next_last

            with _import_lock:
                _import_status["total"] = len(offer_ids)

            for i in range(0, len(offer_ids), 50):
                chunk = offer_ids[i : i + 50]
                info_list = ctx.ozon_gateway.get_products_info(offer_ids=chunk)
                attr_list = ctx.ozon_gateway.get_products_attributes(offer_ids=chunk)
                attr_by_id = {str(a.get("offer_id") or ""): a for a in attr_list if isinstance(a, dict)}

                with ctx.uow:
                    for info in info_list:
                        oid = str(info.get("offer_id") or "").strip()
                        if not oid:
                            continue
                        mapped = ozon_response_to_book_dict(info, attr_by_id.get(oid))
                        existing = ctx.book_repo.get_by_article(oid)
                        if existing is not None:
                            base = existing.to_dict()
                            for k, v in mapped.items():
                                if v and (not base.get(k) or k in ("price", "main_photo_url", "add_photo_urls")):
                                    base[k] = v
                            merged = Book.from_dict(base)
                            merged.ozon_sync_status = OzonSyncStatus.PUBLISHED
                            ctx.book_repo.save(merged)
                            with _import_lock:
                                _import_status["updated"] += 1
                        else:
                            new_book = Book.from_dict(mapped)
                            new_book.status = "IMPORTED"
                            new_book.ozon_sync_status = OzonSyncStatus.PUBLISHED
                            ctx.book_repo.save(new_book)
                            with _import_lock:
                                _import_status["imported"] += 1
                    ctx.uow.commit()

                with _import_lock:
                    _import_status["progress"] = min(i + len(chunk), len(offer_ids))

            with _import_lock:
                _import_status["done"] = True
        except Exception as exc:
            with _import_lock:
                _import_status["error"] = str(exc)
        finally:
            with _import_lock:
                _import_status["running"] = False

    threading.Thread(target=_worker, daemon=True, name="ozon_catalog_import").start()
    return {"status": "started", "running": True}
