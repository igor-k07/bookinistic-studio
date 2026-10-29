"""
image_service.py: Нейросетевая обработка фотографий (удаление фона, отбеливание и повышение резкости).
Работает в пуле потоков ThreadPoolExecutor (max_workers=2) для исключения зависаний интерфейса.
"""

from concurrent.futures import ThreadPoolExecutor
import io
import time
from typing import Optional

from PIL import Image, ImageEnhance, ImageFilter
import rembg

# Ограничиваем пул максимум 2 воркерами, чтобы система оставалась абсолютно отзывчивой
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ai_photo_worker")
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


def _process_image_worker(image_bytes: bytes) -> bytes:
    """Воркер фоновой обработки фото книги нейросетью."""
    t0 = time.time()
    session = get_rembg_session()

    # 1. Удаление фона стола и замена на идеальный белый (255, 255, 255)
    if session:
        out_rgba_bytes = rembg.remove(
            image_bytes,
            session=session,
            bgcolor=(255, 255, 255, 255),
            alpha_matting=False
        )
    else:
        out_rgba_bytes = rembg.remove(
            image_bytes,
            bgcolor=(255, 255, 255, 255),
            alpha_matting=False
        )

    # 2. Открытие в Pillow и финальная посадка на чистый белый фон
    img = Image.open(io.BytesIO(out_rgba_bytes))
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        alpha = img.convert("RGBA").split()[-1]
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.paste(img, mask=alpha)
        img = bg.convert("RGB")
    else:
        img = img.convert("RGB")

    # 3. Легкое повышение резкости букв и фактуры переплета
    try:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=115, threshold=3))
    except Exception:
        pass

    # 4. Сохранение в оптимизированный JPEG (88% качества)
    out_buf = io.BytesIO()
    img.save(out_buf, format="JPEG", quality=88, optimize=True)
    result_bytes = out_buf.getvalue()

    duration = time.time() - t0
    print(f"✨ Нейросетевая обработка фото выполнена за {duration:.2f} сек ({len(image_bytes)} -> {len(result_bytes)} байт)")
    return result_bytes


def process_image_ai(image_bytes: bytes) -> bytes:
    """
    Запускает обработку фото в пуле потоков.
    Возвращает байты обработанного JPEG с белым фоном.
    """
    future = _executor.submit(_process_image_worker, image_bytes)
    return future.result(timeout=25)

