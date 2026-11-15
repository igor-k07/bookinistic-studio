"""
photo_controller.py: Контроллер работы с фото и ИИ (распознавание, классификация, обработка).
"""

from typing import Any, Dict

from config import get_saved_api_key
from core.use_cases.process_photo import ProcessPhotoUseCase
from core.use_cases.recognize_book import RecognizeBookUseCase
from server.router import RequestContext
from services.ai_service import classify_and_group_book_photos
from services.enrichment_service import enrich_book_metadata

recognize_book_use_case = RecognizeBookUseCase()
process_photo_use_case = ProcessPhotoUseCase()


def recognize_book(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/ai_recognize_book: Распознавание книги через Gemini Vision."""
    body = ctx.get_json()
    api_key = (body.get("api_key") or "").strip() or get_saved_api_key()
    images = body.get("images", [])
    has_illustrations = any("иллюстрац" in (img.get("role_name") or "").lower() for img in images) or bool(body.get("has_illustrations"))

    result = recognize_book_use_case.execute(
        images=images,
        api_key=api_key,
        has_illustrations=has_illustrations,
    )
    return {"success": True, "data": result}


def enrich_book(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/enrich_book: Вторичное обогащение метаданных (FantLab / Open Library)."""
    body = ctx.get_json()
    book_in = body.get("book", {})
    has_illustrations = bool(body.get("has_illustrations", True))
    skip_dimensions = bool(body.get("skip_dimensions", True))
    enriched = enrich_book_metadata(book_in, has_illustrations=has_illustrations, skip_dimensions=skip_dimensions)
    return {"success": True, "data": enriched}


def classify_batch(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/ai_classify_batch: Группировка и классификация фото пачки."""
    body = ctx.get_json()
    api_key = (body.get("api_key") or "").strip() or get_saved_api_key()
    if not api_key:
        raise ValueError("API ключ Gemini не введен!")
    photos = body.get("photos", [])
    if not photos:
        raise ValueError("Нет фотографий для классификации")
    items = classify_and_group_book_photos(photos, api_key)
    return {"success": True, "items": items}


def process_photo(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/ai_process_photo: Обработка фото (rembg для обложки, без rembg для текста)."""
    body = ctx.get_json()
    img_val = body.get("image", "")
    if not img_val:
        raise ValueError("Нет изображения для обработки")
    role_str = body.get("role", "other")
    force_rembg = bool(body.get("force_rembg", False))
    return process_photo_use_case.execute(
        image_input=img_val,
        role_str=role_str,
        force_rembg=force_rembg,
    )


def upload_slot_photo(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/s3_upload_slot_photo: Упреждающая фоновая выгрузка фото в Yandex S3 (Шаг 3 спецификации)."""
    from services.s3_service import upload_single_slot_photo
    body = ctx.get_json()
    article = (body.get("article") or "").strip()
    title = (body.get("title") or "").strip()
    slot = (body.get("slot") or "").strip()
    photo_index = int(body.get("photo_index", 1))
    photo_obj = body.get("photo") or body.get("image") or ""
    photo_id = body.get("photo_id", "")

    if not article or not slot or not photo_obj:
        raise ValueError("Не переданы обязательные параметры article, slot или photo")

    s3_url = upload_single_slot_photo(article, title, slot, photo_index, photo_obj)
    if not s3_url:
        return {"success": False, "message": "S3 не настроен или ошибка выгрузки"}

    return {
        "success": True,
        "s3_url": s3_url,
        "photo_id": photo_id,
        "slot": slot,
    }


