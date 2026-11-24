"""
asset_service.py: Сервис управления ассетами (фотокадрами) Bookinistic Photo Engine V2.
Обеспечивает:
- Регистрацию файлов в SQLite-реестре `assets`
- Бинарную запись на диск и быструю генерацию превью (350-400px)
- Неразрушающее параметрическое кадрирование и цепочку трансформаций
- Фоновое ИИ-вырезание фона на чистый белый (rembg)
- Детерминированный рендеринг финальных изображений для Ozon/S3
"""

import io
import json
import os
import shutil
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageOps

from config import BASE_DIR, DB_PATH, SESSION_ASSETS_DIR, VAULT_DIR
from core.domain.enums import AssetStatus
from core.domain.models import AssetItem
from services.db_service import get_db_connection, init_db


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _generate_asset_id() -> str:
    """Генерирует короткий уникальный ID ассета (ast_XXXXXXXX)."""
    return f"ast_{uuid.uuid4().hex[:10]}"


def create_asset_from_bytes(
    file_bytes: bytes,
    filename: str = "photo.jpg",
    book_id: Optional[int] = None,
    book_article: Optional[str] = None,
    slot: Optional[str] = None,
    slot_order: int = 0,
) -> AssetItem:
    """
    Создает новый ассет:
    1. Потоково сохраняет сырой файл на диск в storage/session_assets/<id>/raw.jpg
    2. Генерирует быстрый легковесный thumbnail preview.jpg (макс 400px)
    3. Создает запись в таблице `assets` SQLite
    """
    init_db()
    asset_id = _generate_asset_id()
    asset_dir = _ensure_dir(os.path.join(SESSION_ASSETS_DIR, asset_id))

    raw_path = os.path.join(asset_dir, "raw.jpg")
    preview_path = os.path.join(asset_dir, "preview.jpg")

    # Чтение изображения через Pillow с коррекцией EXIF ориентации
    im = Image.open(io.BytesIO(file_bytes))
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass

    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    elif im.mode == "L":
        im = im.convert("RGB")

    width, height = im.size

    # 1. Сохраняем raw.jpg (быстрое однопроходное кодирование)
    im.save(raw_path, format="JPEG", quality=88, optimize=False)
    file_size = os.path.getsize(raw_path)

    # 2. Генерируем компактный thumbnail preview.jpg (макс 400px)
    thumb = im.copy()
    thumb.thumbnail((400, 400), Image.Resampling.LANCZOS)
    thumb.save(preview_path, format="JPEG", quality=82, optimize=False)

    # 3. Добавляем запись в SQLite
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO assets (
                id, book_id, book_article, slot, slot_order, status, status_message,
                original_path, preview_path, transformations, version,
                file_size_bytes, width, height, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                book_id,
                book_article,
                slot,
                slot_order,
                AssetStatus.UPLOADED.value,
                "",
                raw_path,
                preview_path,
                json.dumps({}),
                1,
                file_size,
                width,
                height,
                now_str,
                now_str,
            ),
        )
        conn.commit()

    return AssetItem(
        id=asset_id,
        book_id=book_id,
        book_article=book_article,
        slot=slot,
        slot_order=slot_order,
        status=AssetStatus.UPLOADED,
        original_path=raw_path,
        preview_path=preview_path,
        file_size_bytes=file_size,
        width=width,
        height=height,
        created_at=now_str,
        updated_at=now_str,
    )


def get_asset(asset_id: str) -> Optional[AssetItem]:
    """Возвращает ассет по ID."""
    init_db()
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if not row:
            return None
        return AssetItem.from_dict(dict(row))


def list_assets(
    book_id: Optional[int] = None,
    book_article: Optional[str] = None,
    unassigned_only: bool = False,
    include_archived: bool = False,
) -> List[AssetItem]:
    """Возвращает список ассетов по фильтрам."""
    init_db()
    query = "SELECT * FROM assets WHERE 1=1"
    params: List[Any] = []

    if unassigned_only:
        query += " AND slot IS NULL"
    elif book_article:
        query += " AND book_article = ?"
        params.append(book_article)
    elif book_id is not None:
        query += " AND book_id = ?"
        params.append(book_id)

    if not include_archived:
        query += " AND status != 'ARCHIVED'"

    query += " ORDER BY slot_order ASC, created_at ASC"

    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [AssetItem.from_dict(dict(r)) for r in rows]


def assign_asset_slot(
    asset_id: str,
    slot: Optional[str],
    book_id: Optional[int] = None,
    book_article: Optional[str] = None,
    slot_order: int = 0,
) -> Optional[AssetItem]:
    """Привязывает ассет к книге и слоту (или отвязывает при slot=None)."""
    init_db()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE assets
            SET slot = ?, book_id = ?, book_article = ?, slot_order = ?, updated_at = ?
            WHERE id = ?
            """,
            (slot, book_id, book_article, slot_order, now_str, asset_id),
        )
        conn.commit()
    return get_asset(asset_id)


def update_asset_transformations(
    asset_id: str,
    crop: Optional[Dict[str, float]] = None,
    rotation: Optional[int] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Optional[AssetItem]:
    """
    Обновляет неразрушающие параметры трансформации ассета.
    Сырые файлы raw.jpg / ai_white.jpg не перезаписываются!
    """
    asset = get_asset(asset_id)
    if not asset:
        return None

    trans = dict(asset.transformations or {})
    if crop is not None:
        trans["crop"] = crop
    if rotation is not None:
        trans["rotation"] = int(rotation)
    if filters is not None:
        cur_filters = trans.get("filters", {})
        cur_filters.update(filters)
        trans["filters"] = cur_filters

    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE assets
            SET transformations = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(trans), AssetStatus.EDITED.value, now_str, asset_id),
        )
        conn.commit()

    return get_asset(asset_id)


def run_ai_background(asset_id: str) -> Dict[str, Any]:
    """
    Выполняет ИИ-вырезание фона через rembg на чистый белый `#FFFFFF`.
    Сохраняет результат в ai_white.jpg и вычисляет координаты идеального контура (+3.5%).
    """
    asset = get_asset(asset_id)
    if not asset:
        return {"success": False, "error": f"Ассет {asset_id} не найден"}

    # Устанавливаем статус AI_PROCESSING
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE assets SET status = ?, updated_at = ? WHERE id = ?",
            (AssetStatus.AI_PROCESSING.value, now_str, asset_id),
        )
        conn.commit()

    try:
        raw_path = asset.original_path
        if not os.path.exists(raw_path):
            raise FileNotFoundError(f"Файл {raw_path} отсутствует на диске")

        with open(raw_path, "rb") as f:
            raw_bytes = f.read()

        from services.image_service import _process_image_worker
        result = _process_image_worker(raw_bytes)
        full_bytes = result.get("image_bytes")
        crop_relative = result.get("crop_relative")

        asset_dir = os.path.dirname(raw_path)
        ai_white_path = os.path.join(asset_dir, "ai_white.jpg")
        with open(ai_white_path, "wb") as f_out:
            f_out.write(full_bytes)

        # Обновляем preview.jpg с белым фоном и вычисленным авто-кропом книги
        thumb = Image.open(io.BytesIO(full_bytes))
        if crop_relative and isinstance(crop_relative, dict):
            tw, th = thumb.size
            cx = max(0, int(crop_relative.get("x", 0) * tw))
            cy = max(0, int(crop_relative.get("y", 0) * th))
            cw = min(tw - cx, int(crop_relative.get("w", 1) * tw))
            ch = min(th - cy, int(crop_relative.get("h", 1) * th))
            if cw > 20 and ch > 20:
                thumb = thumb.crop((cx, cy, cx + cw, cy + ch))
        thumb.thumbnail((400, 400), Image.Resampling.LANCZOS)
        thumb.save(asset.preview_path, format="JPEG", quality=84, optimize=False)

        # Сохраняем в transformations auto-crop от ИИ
        trans = dict(asset.transformations or {})
        if crop_relative:
            trans["ai_crop"] = crop_relative
            if "crop" not in trans:
                trans["crop"] = crop_relative

        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE assets
                SET ai_white_path = ?, transformations = ?, status = ?, status_message = '', updated_at = ?
                WHERE id = ?
                """,
                (ai_white_path, json.dumps(trans), AssetStatus.AI_READY.value, now_str, asset_id),
            )
            conn.commit()

        updated = get_asset(asset_id)
        return {
            "success": True,
            "asset": updated.to_dict() if updated else None,
            "crop_relative": crop_relative,
        }

    except Exception as e:
        mark_asset_error(asset_id, f"Ошибка ИИ: {e}")
        return {"success": False, "error": str(e)}


def render_final_image(
    asset_id: str,
    output_path: str,
    force_dimensions: Optional[Tuple[int, int]] = None,
) -> bool:
    """
    Детерминированный рендеринг итогового JPEG для выгрузки в S3 / Ozon:
    Исходник (ai_white или raw) -> Поворот -> Кроп -> Фильтры -> Финальный срез.
    """
    asset = get_asset(asset_id)
    if not asset:
        return False

    source_path = asset.ai_white_path if (asset.ai_white_path and os.path.exists(asset.ai_white_path)) else asset.original_path
    if not source_path or not os.path.exists(source_path):
        return False

    try:
        im = Image.open(source_path)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")

        trans = asset.transformations or {}

        # 1. Поворот (кардинальный 0/90/180/270 + тонкий)
        rot = int(trans.get("rotation", 0)) % 360
        if rot != 0:
            # Pillow поворачивает против часовой стрелки при rotate(deg), поэтому expand=True и угол 360-rot
            im = im.rotate(360 - rot, expand=True, resample=Image.Resampling.BICUBIC)

        # 2. Кроп (относительный от 0.0 до 1.0)
        crop = trans.get("crop")
        if crop and isinstance(crop, dict):
            w, h = im.size
            cx = max(0, int(crop.get("x", 0) * w))
            cy = max(0, int(crop.get("y", 0) * h))
            cw = int(crop.get("w", 1.0) * w)
            ch = int(crop.get("h", 1.0) * h)
            if cw > 20 and ch > 20:
                im = im.crop((cx, cy, min(w, cx + cw), min(h, cy + ch)))

        # 3. Фильтры (отбеливание, яркость, контраст, насыщенность)
        filters = trans.get("filters", {})
        whiten = float(filters.get("whiten", 0))
        if whiten > 0:
            w_factor = 1.0 + (whiten / 200.0)
            im = ImageEnhance.Brightness(im).enhance(w_factor)

        bright = float(filters.get("brightness", 0))
        if bright != 0:
            factor = 1.0 + (bright / 100.0)
            im = ImageEnhance.Brightness(im).enhance(max(0.2, factor))

        contrast = float(filters.get("contrast", 0))
        if contrast != 0:
            factor = 1.0 + (contrast / 100.0)
            im = ImageEnhance.Contrast(im).enhance(max(0.2, factor))

        sat = float(filters.get("saturation", 0))
        if sat != 0:
            factor = 1.0 + (sat / 100.0)
            im = ImageEnhance.Color(im).enhance(max(0.0, factor))

        # 4. Принудительный ресайз при необходимости
        if force_dimensions:
            im = im.resize(force_dimensions, Image.Resampling.LANCZOS)

        _ensure_dir(os.path.dirname(output_path))
        im.save(output_path, format="JPEG", quality=90, optimize=True)
        return True

    except Exception as e:
        print(f"⚠️ [AssetService] Ошибка рендеринга ассета {asset_id}: {e}", flush=True)
        return False


def mark_asset_s3(asset_id: str, s3_url: str, s3_etag: str = "", version: int = 1) -> None:
    """Фиксирует успешную выгрузку ассета в Yandex S3 CDN."""
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE assets
            SET s3_url = ?, s3_etag = ?, version = ?, status = ?, status_message = '', updated_at = ?
            WHERE id = ?
            """,
            (s3_url, s3_etag, version, AssetStatus.S3_READY.value, now_str, asset_id),
        )
        conn.commit()


def mark_asset_error(asset_id: str, error_message: str) -> None:
    """Устанавливает статус ERROR с сохранением понятной ошибки для оператора."""
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE assets
            SET status = ?, status_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (AssetStatus.ERROR.value, error_message[:250], now_str, asset_id),
        )
        conn.commit()


def delete_asset(asset_id: str) -> bool:
    """Удаляет ассет с диска и из базы данных."""
    init_db()
    asset_dir = os.path.join(SESSION_ASSETS_DIR, asset_id)
    if os.path.exists(asset_dir):
        try:
            shutil.rmtree(asset_dir)
        except Exception:
            pass

    with get_db_connection() as conn:
        conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        conn.commit()
    return True


def get_storage_stats() -> Dict[str, Any]:
    """Возвращает статистику занятого дискового пространства."""
    def _dir_size(path: str) -> int:
        total = 0
        if not os.path.exists(path):
            return 0
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if not os.path.islink(fp):
                    try:
                        total += os.path.getsize(fp)
                    except Exception:
                        pass
        return total

    session_assets_bytes = _dir_size(SESSION_ASSETS_DIR)
    vault_bytes = _dir_size(VAULT_DIR)
    total_bytes = session_assets_bytes + vault_bytes

    init_db()
    with get_db_connection() as conn:
        asset_count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        archived_count = conn.execute("SELECT COUNT(*) FROM assets WHERE status = 'ARCHIVED'").fetchone()[0]
        book_count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]

    return {
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "total_gb": round(total_bytes / (1024 * 1024 * 1024), 3),
        "session_assets_mb": round(session_assets_bytes / (1024 * 1024), 2),
        "vault_mb": round(vault_bytes / (1024 * 1024), 2),
        "asset_count": asset_count,
        "archived_asset_count": archived_count,
        "book_count": book_count,
    }

