"""
session_controller.py: Контроллер мобильных загрузок и черновиков сессий.
"""

import base64
import os
import time
from typing import Any, Dict

from config import DRAFT_FILE, INBOX_DIR, get_draft_file_path
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
    import services.asset_service as asset_service
    for idx, img in enumerate(images):
        fname = f"mobile_batch_{session_ts}_{chunk_index}_{idx+1}.jpg"
        p = os.path.join(INBOX_DIR, fname)
        raw_b64 = img.get("data", "")
        if raw_b64:
            clean_b64 = raw_b64.split(",", 1)[1] if "," in raw_b64 else raw_b64
            try:
                raw_bytes = base64.b64decode(clean_b64)
                with open(p, "wb") as f:
                    f.write(raw_bytes)
                # Регистрируем в Photo Engine V2 SQLite
                asset = asset_service.create_asset_from_bytes(raw_bytes, filename=img.get("name", fname))
                img["id"] = asset.id
                img["preview_url"] = f"/api/assets/{asset.id}/preview"
                img["full_url"] = f"/api/assets/{asset.id}/full"
                img["preview"] = img["preview_url"]
                img["cameraOriginal"] = img["full_url"]
                img["rawOriginal"] = img["full_url"]
            except Exception as e:
                print(f"⚠️ Ошибка сохранения мобильного фото: {e}")

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
    """GET /api/get_session_draft: Чтение черновика сессии с автоматическим восстановлением ссылок на фото."""
    draft_file = get_draft_file_path()
    if os.path.exists(draft_file) and os.path.getsize(draft_file) > 5:
        try:
            with open(draft_file, "r", encoding="utf-8") as f:
                import json
                draft = json.load(f)

            if isinstance(draft, dict) and draft.get("booksSession"):
                photo_pool = draft.get("photoPool") or []
                pool_map = {p["id"]: p for p in photo_pool if isinstance(p, dict) and "id" in p}
                draft_modified = False

                from services.vault_service import reopen_book_from_vault, SESSION_PHOTOS_DIR

                for b in draft["booksSession"]:
                    if not isinstance(b, dict):
                        continue
                    b_id = b.get("id")
                    art = b.get("article") or (b.get("formData") or {}).get("article")

                    slots = b.get("slots") or {}
                    needs_healing = False

                    def _is_broken(photo_item: Any) -> bool:
                        if not photo_item or not isinstance(photo_item, dict):
                            return False
                        pid = photo_item.get("id")
                        pool_p = pool_map.get(pid) or photo_item
                        prev = pool_p.get("preview") or ""
                        if not prev:
                            return True
                        if "/session_photos/" in prev:
                            fname = os.path.basename(prev.split("?")[0])
                            if not os.path.exists(os.path.join(SESSION_PHOTOS_DIR, fname)):
                                return True
                        return False

                    if _is_broken(slots.get("cover_front")):
                        needs_healing = True
                    for s in ("cover_back", "info_pages", "illustrations", "mantra_defects"):
                        for itm in (slots.get(s) or []):
                            if _is_broken(itm):
                                needs_healing = True
                                break
                        if needs_healing:
                            break

                    if needs_healing and art:
                        try:
                            reopened = reopen_book_from_vault(art)
                            if reopened and reopened.get("slots"):
                                b["slots"] = reopened["slots"]
                                b["isSavedToExcel"] = True
                                b["isEditMode"] = True
                                slots = reopened["slots"]
                                for slot_val in slots.values():
                                    items = slot_val if isinstance(slot_val, list) else ([slot_val] if slot_val else [])
                                    for p_obj in items:
                                        if isinstance(p_obj, dict) and p_obj.get("id"):
                                            pool_map[p_obj["id"]] = p_obj
                                draft_modified = True
                        except Exception as e_heal:
                            print(f"⚠️ Ошибка авто-восстановления книги {art}: {e_heal}")

                    # Гарантируем строгую привязку всех слотовых фото к id книги
                    for slot_name, slot_val in (b.get("slots") or {}).items():
                        items = slot_val if isinstance(slot_val, list) else ([slot_val] if slot_val else [])
                        for p_obj in items:
                            if isinstance(p_obj, dict) and p_obj.get("id"):
                                pid = p_obj["id"]
                                p_obj["assignedBookId"] = b_id
                                p_obj["assignedSlot"] = slot_name
                                if pid in pool_map:
                                    if pool_map[pid].get("assignedBookId") != b_id or pool_map[pid].get("assignedSlot") != slot_name:
                                        pool_map[pid]["assignedBookId"] = b_id
                                        pool_map[pid]["assignedSlot"] = slot_name
                                        draft_modified = True
                                else:
                                    pool_map[pid] = p_obj
                                    draft_modified = True

                if draft_modified:
                    draft["photoPool"] = list(pool_map.values())
                    try:
                        with open(draft_file, "w", encoding="utf-8") as f_out:
                            json.dump(draft, f_out, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

            return draft
        except Exception as e_dr:
            print(f"⚠️ Ошибка чтения черновика: {e_dr}")
    return {"has_draft": False}


def clear_session_draft(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/clear_session_draft: Очистка черновика сессии и сброс мобильной очереди."""
    from server.state import reset_mobile_state
    reset_mobile_state()
    clear_session_draft_storage()
    return {"success": True}


