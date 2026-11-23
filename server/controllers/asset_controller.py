"""
asset_controller.py: Контроллер для REST API управления ассетами Bookinistic Photo Engine V2.
Обрабатывает:
- Бинарную загрузку multipart/form-data (смартфон / десктоп)
- Назначение в слоты, неразрушающие трансформации и вызов rembg
- Получение статистики диска и сборку мусора
- Повторное открытие книги на редактирование (Re-open)
"""

import base64
import email
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from core.domain.enums import AssetStatus
from server.router import RequestContext
from server.state import record_mobile_upload
import services.asset_service as asset_service


def _parse_multipart(content_type_header: str, body_bytes: bytes) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """Разбирает тело multipart/form-data запроса."""
    full_data = f"Content-Type: {content_type_header}\r\n\r\n".encode("latin1") + body_bytes
    msg = email.message_from_bytes(full_data)
    fields: Dict[str, str] = {}
    files: List[Dict[str, Any]] = []

    if msg.is_multipart():
        for part in msg.get_payload():
            field_name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                files.append({
                    "field_name": field_name,
                    "filename": filename,
                    "bytes": payload,
                    "content_type": part.get_content_type(),
                })
            elif field_name:
                fields[field_name] = payload.decode("utf-8", errors="replace")

    return fields, files


def _format_asset_response(asset) -> Dict[str, Any]:
    """Форматирует ассет для фронтенда с удобными URL превью и полного кадра."""
    d = asset.to_dict()
    d["preview_url"] = f"/api/assets/{asset.id}/preview"
    d["full_url"] = f"/api/assets/{asset.id}/full"
    # Для обратной совместимости с существующим UI (state.js/pipeline.js)
    d["preview"] = d["preview_url"]
    d["cameraOriginal"] = d["full_url"]
    d["rawOriginal"] = d["full_url"]
    if asset.ai_white_path:
        d["aiWhiteOriginal"] = d["full_url"]
    return d


def upload_assets(ctx: RequestContext) -> Dict[str, Any]:
    """
    POST /api/assets/upload: Загрузка одной или нескольких фотографий (бинарный FormData или Base64).
    """
    handler_headers = ctx.handler.headers
    content_type = handler_headers.get("Content-Type", "")

    uploaded_assets = []
    book_id: Optional[int] = None
    book_article: Optional[str] = None
    slot: Optional[str] = None
    source = "desktop"

    if "multipart/form-data" in content_type.lower():
        fields, files = _parse_multipart(content_type, ctx.body)
        book_id_raw = fields.get("book_id")
        if book_id_raw:
            try:
                book_id = int(book_id_raw)
            except Exception:
                pass
        book_article = fields.get("book_article") or fields.get("article")
        slot = fields.get("slot")
        source = fields.get("source", "desktop")

        for f in files:
            fb = f.get("bytes")
            if not fb:
                continue
            fname = f.get("filename") or "photo.jpg"
            asset = asset_service.create_asset_from_bytes(
                file_bytes=fb,
                filename=fname,
                book_id=book_id,
                book_article=book_article,
                slot=slot,
            )
            uploaded_assets.append(_format_asset_response(asset))

    else:
        # Fallback: JSON с base64 для обратной совместимости
        body = ctx.get_json()
        source = body.get("source", "desktop")
        book_id = body.get("book_id")
        book_article = body.get("book_article")
        slot = body.get("slot")

        images = body.get("images", [])
        if not images and body.get("image"):
            images = [body["image"]]

        for idx, item in enumerate(images):
            raw_data = item.get("data") if isinstance(item, dict) else item
            fname = item.get("name") if isinstance(item, dict) else f"photo_{idx}.jpg"
            if not raw_data:
                continue
            b64_str = raw_data.split(",", 1)[1] if "," in str(raw_data) else str(raw_data)
            try:
                fb = base64.b64decode(b64_str)
                asset = asset_service.create_asset_from_bytes(
                    file_bytes=fb,
                    filename=fname,
                    book_id=book_id,
                    book_article=book_article,
                    slot=slot,
                )
                uploaded_assets.append(_format_asset_response(asset))
            except Exception as e:
                print(f"⚠️ Ошибка декодирования base64 в upload_assets: {e}")

    # Если загрузка пришла от мобильного клиента — регистрируем событие для десктопа
    if source == "mobile" and uploaded_assets:
        record_mobile_upload(session_ts=int(time.time()), images=uploaded_assets)

    return {
        "success": True,
        "count": len(uploaded_assets),
        "assets": uploaded_assets,
    }


def list_assets_api(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/assets/list: Список ассетов по фильтрам."""
    book_id_raw = ctx.get_query("book_id")
    book_id = int(book_id_raw) if book_id_raw else None
    book_article = ctx.get_query("book_article") or ctx.get_query("article")
    unassigned = ctx.get_query("unassigned", "false").lower() in ("true", "1")
    include_archived = ctx.get_query("include_archived", "false").lower() in ("true", "1")

    items = asset_service.list_assets(
        book_id=book_id,
        book_article=book_article,
        unassigned_only=unassigned,
        include_archived=include_archived,
    )
    return {
        "success": True,
        "count": len(items),
        "assets": [_format_asset_response(a) for a in items],
    }


def get_asset_api(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/assets/get: Получение одного ассета по ID."""
    asset_id = ctx.get_query("id") or ""
    if not asset_id:
        raise ValueError("Не передан параметр id")
    asset = asset_service.get_asset(asset_id)
    if not asset:
        return {"success": False, "error": f"Ассет {asset_id} не найден"}
    return {"success": True, "asset": _format_asset_response(asset)}


def assign_slot_api(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/assets/assign: Назначение ассета в слот книги."""
    body = ctx.get_json()
    asset_id = (body.get("asset_id") or body.get("id") or "").strip()
    slot = body.get("slot")  # None для отвязки
    book_id = body.get("book_id")
    book_article = body.get("book_article") or body.get("article")
    slot_order = int(body.get("slot_order") or 0)

    if not asset_id:
        raise ValueError("Не указан asset_id")

    updated = asset_service.assign_asset_slot(
        asset_id=asset_id,
        slot=slot,
        book_id=int(book_id) if book_id is not None else None,
        book_article=book_article,
        slot_order=slot_order,
    )
    if not updated:
        return {"success": False, "error": f"Ассет {asset_id} не найден"}
    return {"success": True, "asset": _format_asset_response(updated)}


def transform_asset_api(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/assets/transform: Обновление неразрушающих параметров кропа, угла и фильтров."""
    body = ctx.get_json()
    asset_id = (body.get("asset_id") or body.get("id") or "").strip()
    crop = body.get("crop")
    rotation = body.get("rotation")
    filters = body.get("filters")

    if not asset_id:
        raise ValueError("Не указан asset_id")

    updated = asset_service.update_asset_transformations(
        asset_id=asset_id,
        crop=crop,
        rotation=rotation,
        filters=filters,
    )
    if not updated:
        return {"success": False, "error": f"Ассет {asset_id} не найден"}
    return {"success": True, "asset": _format_asset_response(updated)}


def run_ai_api(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/assets/run_ai: Запуск нейросетевого вырезания фона rembg на чистый белый `#FFFFFF`."""
    body = ctx.get_json()
    asset_id = (body.get("asset_id") or body.get("id") or "").strip()
    if not asset_id:
        raise ValueError("Не указан asset_id")

    res = asset_service.run_ai_background(asset_id)
    return res


def delete_asset_api(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/assets/delete: Удаление ассета."""
    body = ctx.get_json()
    asset_id = (body.get("asset_id") or body.get("id") or "").strip()
    if not asset_id:
        raise ValueError("Не указан asset_id")

    ok = asset_service.delete_asset(asset_id)
    return {"success": ok}


def storage_stats_api(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/storage/stats: Статистика хранилища диска."""
    stats = asset_service.get_storage_stats()
    return {"success": True, "stats": stats}


def cleanup_storage_api(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/storage/cleanup: Запуск сборщика мусора и ступенчатой очистки диска."""
    from core.use_cases.cleanup_temp_files import CleanupTempFilesUseCase
    use_case = CleanupTempFilesUseCase()
    res = use_case.execute(max_age_hours=24.0, dry_run=False)
    res["stats"] = asset_service.get_storage_stats()
    return res


def reopen_book_api(ctx: RequestContext) -> Dict[str, Any]:
    """
    POST /api/books/reopen: Восстанавливает сохраненную из каталога книгу обратно в активную сессию со всеми исходниками и рамками.
    """
    body = ctx.get_json()
    article = (body.get("article") or "").strip()
    if not article:
        raise ValueError("Не указан артикул книги для открытия")

    from services.vault_service import reopen_book_from_vault
    book_session_entry = reopen_book_from_vault(article)
    if not book_session_entry:
        return {"success": False, "error": f"Книга {article} не найдена в хранилище books_vault"}

    return {
        "success": True,
        "book": book_session_entry,
        "message": f"Книга {article} успешно открыта для редактирования",
    }
