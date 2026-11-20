"""
session_controller.py: Контроллер мобильных загрузок и черновиков сессий.
"""

import base64
import os
import time
from typing import Any, Dict

from config import DRAFT_FILE, INBOX_DIR
from server.router import RequestContext
from server.state import add_mobile_chunk, check_mobile_events
from services.vault_service import clear_session_draft_storage, save_session_draft_file


def mobile_upload(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/mobile_upload: Прием порции фото со смартфона."""
    body = ctx.get_json()
    images = body.get("images", [])
    session_id = str(body.get("session_id", ""))
    chunk_index = int(body.get("chunk_index", 0))
    total_chunks = int(body.get("total_chunks", 1))
    is_last_chunk = bool(body.get("is_last_chunk", total_chunks <= 1))

    if not images and not is_last_chunk:
        raise ValueError("Нет изображений в запросе")

    session_ts = int(time.time())
    for idx, img in enumerate(images):
        fname = f"mobile_batch_{session_ts}_{chunk_index}_{idx+1}.jpg"
        p = os.path.join(INBOX_DIR, fname)
        with open(p, "wb") as f:
            f.write(base64.b64decode(img.get("data", "")))

    return add_mobile_chunk(session_id, chunk_index, total_chunks, is_last_chunk, images)


def check_mobile_event(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/check_mobile_event: Long-polling мобильных событий."""
    last_id = int(ctx.get_query("last_id", "0"))
    return check_mobile_events(last_id)


def save_session_draft(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/save_session_draft: Автосохранение черновика сессии."""
    draft_data = ctx.get_json()
    updated_urls = save_session_draft_file(draft_data)
    return {"success": True, "updated_urls": updated_urls}


def get_session_draft(ctx: RequestContext) -> Any:
    """GET /api/get_session_draft: Чтение черновика сессии."""
    if os.path.exists(DRAFT_FILE) and os.path.getsize(DRAFT_FILE) > 5:
        try:
            with open(DRAFT_FILE, "r", encoding="utf-8") as f:
                import json
                return json.load(f)
        except Exception:
            pass
    return {"has_draft": False}


def clear_session_draft(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/clear_session_draft: Очистка черновика сессии и сброс мобильной очереди."""
    from server.state import reset_mobile_state
    reset_mobile_state()
    clear_session_draft_storage()
    return {"success": True}


