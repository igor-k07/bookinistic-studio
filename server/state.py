"""
state.py: Управление потокобезопасным состоянием сервера (события мобильной загрузки).
"""

import threading
from typing import Any, Dict, List

_latest_mobile_event: Dict[str, Any] = {
    "event_id": 0,
    "timestamp": 0,
    "images": []
}
_event_lock = threading.Lock()


def record_mobile_upload(session_ts: int, images: List[Dict[str, Any]]) -> int:
    """Регистрирует новую пачку фотографий, загруженную со смартфона."""
    global _latest_mobile_event
    with _event_lock:
        _latest_mobile_event["event_id"] += 1
        _latest_mobile_event["timestamp"] = session_ts
        _latest_mobile_event["images"] = images
        return _latest_mobile_event["event_id"]


def check_mobile_events(last_id: int) -> Dict[str, Any]:
    """Проверяет наличие новых событий мобильной загрузки относительно last_id."""
    with _event_lock:
        if _latest_mobile_event["event_id"] > last_id:
            return {
                "has_new": True,
                "event_id": _latest_mobile_event["event_id"],
                "images": _latest_mobile_event["images"]
            }
        else:
            return {"has_new": False, "event_id": last_id}

