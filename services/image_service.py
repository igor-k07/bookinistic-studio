"""
image_service.py: Нейросетевая обработка фотографий:
1. Авто-поворот книги вертикально лицевой читаемой стороной вверх (Gemini Vision + геометрия).
2. Вырезание фона стола на чистый белый Ozon (#FFFFFF).
3. Автоматическое определение безопасной рамки контура книги для быстрого кадрирования в студии.
Работает в пуле потоков ThreadPoolExecutor (max_workers=2) для исключения зависаний интерфейса.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import time
from typing import Optional
import urllib.request
import os

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import rembg

# Ограничиваем пул максимум 2 воркерами, чтобы система оставалась абсолютно отзывчивой
# Configurable number of workers for parallel image processing (default 4)
MAX_WORKERS = int(os.getenv('MAX_IMAGE_WORKERS', '4'))
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="ai_photo_worker")
_rembg_session = None


def get_rembg_session():
    """Возвращает кэшированную сессию rembg."""
    global _rembg_session
    if _rembg_session is None:
        try:
            _rembg_session = rembg.new_session("u2net")
        except Exception as e:
            print(f"Ошибка создания rembg сессии: {e}")
            _rembg_session = False
    return _rembg_session if _rembg_session is not False else None


def detect_book_rotation(img: Image.Image) -> int:
    """
    Определяет необходимый угол поворота по часовой стрелке (0, 90, 180, 270),
    чтобы обложка или страница книги стояла вертикально и текст читался слева направо.
    Использует сверхбыстрый запрос в Gemini Vision (1-2 сек) с геометрическим fallback.
    """
    try:
        from config import get_saved_api_key
        api_key = get_saved_api_key()
        if api_key:
            thumb = img.copy()
            thumb.thumbnail((360, 360))
            buf = io.BytesIO()
            thumb.save(buf, format="JPEG", quality=70)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")

            payload = {
                "contents": [{
                    "parts": [
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                        {"text": "Determine how many degrees CLOCKWISE (0, 90, 180, or 270) this book cover or page must be rotated so that the text and cover are oriented vertically, upright and readable (not upside down, not sideways). Return JSON: {\"rotate_clockwise\": 0|90|180|270}"}
                    ]
                }],
                "generationConfig": {"response_mime_type": "application/json", "temperature": 0.0}
            }

            models = ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-flash-latest"]
            for m in models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(text)
                        deg = int(parsed.get("rotate_clockwise", 0))
                        if deg in (0, 90, 180, 270):
                            return deg
                except Exception:
                    continue
    except Exception as e:
        print(f"Ошибка проверки ориентации через Gemini: {e}")

    # Fallback по соотношению сторон: если ширина ощутимо больше высоты, скорее всего снимок на боку
    w, h = img.size
    return 90 if w > h * 1.15 else 0


def _process_image_worker(image_bytes: bytes) -> dict:
    """
    Воркер фоновой обработки фото книги:
    1. Исправление EXIF и авто-поворот вертикально верхом вверх.
    2. Вырезание фона стола нейросетью rembg на чистый белый Ozon (#FFFFFF).
    3. Вычисление координат рамки контура книги с безопасным отступом (+3.5%).
    Возвращает полный кадр на белом фоне (без обрезки) и координаты рамки для студии.
    """
    t0 = time.time()

    # 1. Загрузка исходника и исправление ориентации сенсора смартфона (EXIF)
    raw_img = Image.open(io.BytesIO(image_bytes))
    raw_img = ImageOps.exif_transpose(raw_img)

    # 2. Авто-поворот отключен: кадр сохраняет оригинальную ориентацию камеры
    rot_deg = 0

    buf_oriented = io.BytesIO()
    raw_img.convert("RGB").save(buf_oriented, format="JPEG", quality=92)
    oriented_bytes = buf_oriented.getvalue()

    # 3. Удаление фона стола нейросетью с получением альфа-маски книги
    session = get_rembg_session()
    if session:
        out_rgba_bytes = rembg.remove(oriented_bytes, session=session, alpha_matting=False)
    else:
        out_rgba_bytes = rembg.remove(oriented_bytes, alpha_matting=False)

    img_rgba = Image.open(io.BytesIO(out_rgba_bytes)).convert("RGBA")
    alpha = img_rgba.split()[-1]
    bbox = alpha.getbbox()  # (left, upper, right, lower)

    # 4. Посадка на идеальный белый фон (#FFFFFF)
    bg_full = Image.new("RGBA", img_rgba.size, (255, 255, 255, 255))
    bg_full.paste(img_rgba, mask=alpha)
    full_rgb = bg_full.convert("RGB")

    w_orig, h_orig = img_rgba.size

    # 5. Вычисление безопасной рамки контура книги (+3.5% отступа с каждой стороны)
    crop_relative = None
    if bbox:
        left, upper, right, lower = bbox
        bw = right - left
        bh = lower - upper
        if bw > 40 and bh > 40:
            pad_x = max(16, int(bw * 0.035))
            pad_y = max(16, int(bh * 0.035))
            c_left = max(0, left - pad_x)
            c_upper = max(0, upper - pad_y)
            c_right = min(w_orig, right + pad_x)
            c_lower = min(h_orig, lower + pad_y)

            crop_relative = {
                "x": round(c_left / w_orig, 4),
                "y": round(c_upper / h_orig, 4),
                "w": round((c_right - c_left) / w_orig, 4),
                "h": round((c_lower - c_upper) / h_orig, 4)
            }

    # 6. Легкое повышение резкости букв и переплета
    try:
        full_rgb = full_rgb.filter(ImageFilter.UnsharpMask(radius=1.2, percent=115, threshold=3))
    except Exception:
        pass

    # 7. Сохранение полного кадра на белом фоне (89% качества)
    buf_full = io.BytesIO()
    full_rgb.save(buf_full, format="JPEG", quality=89, optimize=True)
    full_bytes = buf_full.getvalue()

    duration = time.time() - t0
    print(f"✨ Обработка фото: чистый белый фон и рамка книги готовы за {duration:.2f} сек")

    return {
        "image_bytes": full_bytes,
        "crop_relative": crop_relative,
        "rotation": rot_deg
    }


def process_image_ai(image_bytes: bytes) -> dict:
    """
    Запускает обработку фото в пуле потоков.
    Возвращает словарь с полным кадром на белом фоне (image_bytes), координатами рамки и углом поворота.
    """
    future = _executor.submit(_process_image_worker, image_bytes)
    return future.result(timeout=40)
