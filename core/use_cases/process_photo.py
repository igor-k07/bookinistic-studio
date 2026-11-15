"""
process_photo.py: Сценарий (Use Case) обработки фотографий книги.
Строго соблюдает регламент п. 3.2 спецификации:
- Обложка и задник: удаление фона стола на чистый белый (#FFFFFF) + кадрирование 3:4.
- Титулы, текст, мантры, дефекты и иллюстрации: БЕЗ вырезания фона, только нормализация и сжатие.
- Ручной режим: возможность принудительного вырезания по флагу force_rembg.
"""

import base64
import io
from typing import Any, Dict, Optional

from PIL import Image, ImageFilter, ImageOps

from core.domain.enums import PhotoRole
from services.image_service import process_image_ai
from services.vault_service import resolve_photo_bytes


class ProcessPhotoUseCase:
    """
    Интеллектуальный процессор фотографий книги с соблюдением ролевых правил спецификации.
    """

    def execute(
        self,
        image_input: Any,
        role_str: str = "other",
        force_rembg: bool = False,
    ) -> Dict[str, Any]:
        """
        Обрабатывает фотографию в соответствии с её ролью.
        """
        img_bytes = resolve_photo_bytes(image_input)
        if not img_bytes:
            raise ValueError("Не удалось прочитать байты изображения")

        role = PhotoRole.from_str(role_str)

        # Проверка правила вырезания фона (п. 3.2 спецификации)
        should_cut_bg = role.should_remove_background or force_rembg

        if should_cut_bg:
            # Для обложки/задника или при явном запросе букиниста: rembg + отбеливание + рамка
            result = process_image_ai(img_bytes)
            if isinstance(result, dict):
                full_img_bytes = result.get("image_bytes") or result.get("full_bytes")
                out_b64 = "data:image/jpeg;base64," + base64.b64encode(full_img_bytes).decode("ascii")
                crop_rel = result.get("crop_relative")
                rot = result.get("rotation", 0)
            else:
                out_b64 = "data:image/jpeg;base64," + base64.b64encode(result).decode("ascii")
                crop_rel = None
                rot = 0
            return {
                "success": True,
                "image": out_b64,
                "crop_relative": crop_rel,
                "rotation": rot,
                "rembg_applied": True,
            }
        else:
            # Для титулов, текста, мантры, иллюстраций и дефектов:
            # КАТЕГОРИЧЕСКИ БЕЗ rembg! Сохраняем разворот и естественный вид книги.
            raw_img = Image.open(io.BytesIO(img_bytes))
            raw_img = ImageOps.exif_transpose(raw_img).convert("RGB")

            # Легкое повышение резкости текста
            try:
                raw_img = raw_img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=105, threshold=3))
            except Exception:
                pass

            buf = io.BytesIO()
            raw_img.save(buf, format="JPEG", quality=90, optimize=True)
            out_bytes = buf.getvalue()
            out_b64 = "data:image/jpeg;base64," + base64.b64encode(out_bytes).decode("ascii")

            return {
                "success": True,
                "image": out_b64,
                "crop_relative": None,
                "rotation": 0,
                "rembg_applied": False,
            }

