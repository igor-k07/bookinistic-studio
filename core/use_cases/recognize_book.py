"""
recognize_book.py: Сценарий (Use Case) интеллектуального распознавания книги.
Реализует строгую фильтрацию кадров (только обложка/титулы/мантра, без дефектов и иллюстраций),
вызов Gemini Vision и вторичное библиографическое обогащение (FantLab).
"""

from typing import Any, Dict, List, Optional

from config import get_saved_api_key
from core.domain.enums import PhotoRole
from services.ai_service import call_gemini_vision
from services.db_service import reconcile_with_references
from services.enrichment_service import enrich_book_metadata


class RecognizeBookUseCase:
    """
    Интеллектуальный конвейер распознавания книги из фотокадров.
    """

    def execute(
        self,
        images: List[Dict[str, Any]],
        api_key: Optional[str] = None,
        has_illustrations: bool = False,
    ) -> Dict[str, Any]:
        """
        Запускает распознавание и обогащение метаданных книги.
        """
        active_key = (api_key or "").strip() or get_saved_api_key()
        if not active_key:
            raise ValueError("API ключ Gemini не введен! Нажмите «Ввести API ключ» в интерфейсе.")

        if not images:
            raise ValueError("Нет изображений для распознавания! Добавьте фото в слот или выберите в ленте.")

        # 1. СТРОГАЯ ФИЛЬТРАЦИЯ ПО РОЛЯМ (п. 4.1 спецификации):
        # В Gemini Vision отправляются СТРОГО: обложка, титульный лист, оборот, мантра/колофон.
        # Иллюстрации и дефекты отфильтровываются, чтобы не тратить токены и не путать модель.
        filtered_images = []
        for img in images:
            role_str = str(img.get("role_name") or img.get("role") or "").strip()
            role = PhotoRole.from_str(role_str)
            if role.is_ai_vision_candidate:
                filtered_images.append(img)
            else:
                # Если роль не определена или это не иллюстрация/дефект, но изображение передано в инфо-слоте
                low_name = role_str.lower()
                if "иллюстрац" not in low_name and "дефект" not in low_name and "damage" not in low_name:
                    filtered_images.append(img)

        # Если после фильтрации список пуст (например, передан неизвестный формат слота), берем исходный
        images_to_send = filtered_images if filtered_images else images

        print(f"🧠 [RecognizeBookUseCase] Отправка в Gemini Vision: {len(images_to_send)} из {len(images)} фото (отфильтрованы дефекты/иллюстрации)...", flush=True)

        # 2. Вызов Gemini Vision
        raw_result = call_gemini_vision(images_to_send, active_key)

        # 3. Вторичная сверка и библиографическое обогащение (FantLab / Open Library)
        try:
            enriched = enrich_book_metadata(raw_result, has_illustrations=has_illustrations)
        except Exception as enrich_err:
            print(f"⚠️ [RecognizeBookUseCase] Обогащение FantLab пропущено: {enrich_err}", flush=True)
            enriched = raw_result

        # 4. Нормализация под стандарты магазина Ozon (397 брендов, 1310 авторов)
        try:
            final_result = reconcile_with_references(enriched)
        except Exception as rec_err:
            print(f"⚠️ [RecognizeBookUseCase] Канонизация пропущена: {rec_err}", flush=True)
            final_result = enriched

        return final_result

