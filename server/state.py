"""
state.py: Управление потокобезопасным состоянием сервера (события мобильной загрузки).
Поддержка как одиночной передачи пачек, так и потоковой загрузки порциями (chunked upload).
"""

import threading
import time
from typing import Any, Dict, List

_latest_mobile_event: Dict[str, Any] = {
    "event_id": 0,
    "timestamp": 0,
    "images": []
}
_upload_sessions: Dict[str, Dict[str, Any]] = {}
_event_lock = threading.Lock()


def record_mobile_upload(session_ts: int, images: List[Dict[str, Any]]) -> int:
    """Регистрирует новую пачку фотографий, загруженную со смартфона (одиночный запрос)."""
    global _latest_mobile_event
    with _event_lock:
        _latest_mobile_event["event_id"] += 1
        _latest_mobile_event["timestamp"] = session_ts
        _latest_mobile_event["images"] = images
        return _latest_mobile_event["event_id"]


def add_mobile_chunk(
    session_id: str,
    chunk_index: int,
    total_chunks: int,
    is_last_chunk: bool,
    images: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Принимает порцию фотографий от мобильного клиента.
    Если это последняя порция сессии, объединяет все фото сессии и регистрирует единое событие для десктопа.
    """
    global _upload_sessions, _latest_mobile_event
    now = time.time()
    session_ts = int(now)

    with _event_lock:
        # Очистка устаревших незавершенных сессий (старше 10 минут)
        stale_keys = [k for k, v in _upload_sessions.items() if now - v.get("updated_at", 0) > 600]
        for k in stale_keys:
            _upload_sessions.pop(k, None)

        # Одиночный запрос без сессии или единственный чанк
        if not session_id or total_chunks <= 1 or (is_last_chunk and session_id not in _upload_sessions):
            _latest_mobile_event["event_id"] += 1
            _latest_mobile_event["timestamp"] = session_ts
            _latest_mobile_event["images"] = images
            return {
                "success": True,
                "event_id": _latest_mobile_event["event_id"],
                "total_count": len(images),
                "is_complete": True
            }

        # Многопорционная сессия
        if session_id not in _upload_sessions:
            _upload_sessions[session_id] = {
                "created_at": now,
                "updated_at": now,
                "images": []
            }

        session_entry = _upload_sessions[session_id]
        session_entry["updated_at"] = now
        session_entry["images"].extend(images)

        if is_last_chunk or (chunk_index + 1 >= total_chunks):
            # Сессия завершена: объединяем и передаем в рабочий конвейер десктопа
            all_images = session_entry["images"]
            _upload_sessions.pop(session_id, None)

            _latest_mobile_event["event_id"] += 1
            _latest_mobile_event["timestamp"] = session_ts
            _latest_mobile_event["images"] = all_images
            return {
                "success": True,
                "event_id": _latest_mobile_event["event_id"],
                "total_count": len(all_images),
                "is_complete": True
            }
        else:
            return {
                "success": True,
                "chunk_index": chunk_index,
                "received_count": len(images),
                "accumulated_count": len(session_entry["images"]),
                "is_complete": False
            }


def check_mobile_events(last_id: int) -> Dict[str, Any]:
    """Проверяет наличие новых событий мобильной загрузки относительно last_id."""
    with _event_lock:
        if _latest_mobile_event["event_id"] > last_id:
            # Защита от воскрешения старых фото при открытии новой вкладки десктопа:
            # если событие старше 10 минут и last_id == 0, не отправляем его заново
            if last_id == 0 and _latest_mobile_event["timestamp"] > 0 and (time.time() - _latest_mobile_event["timestamp"] > 600):
                return {"has_new": False, "event_id": _latest_mobile_event["event_id"]}
            return {
                "has_new": True,
                "event_id": _latest_mobile_event["event_id"],
                "images": _latest_mobile_event["images"]
            }
        else:
            return {"has_new": False, "event_id": last_id}
