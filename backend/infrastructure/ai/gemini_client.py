"""Google Gemini Vision AI client for Bookinistic Studio 2.0.

Architectural Guarantees:
- API key passed strictly via 'x-goog-api-key' header (never in URL or query params).
- Resizes incoming images to max 1200px with Pillow exif_transpose.
- Robust tenacity retries on 429 / 503; fail-fast on API_KEY_INVALID.
- Thinking-safe response part extraction (skips 'thought': true parts).
- Automatic recitation recovery retry.
- Configurable model cascade from AppSettings.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from PIL import Image, ImageOps
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.config.settings import AppSettings
from backend.domain.exceptions import AuthenticationError, ExternalServiceError
from backend.domain.ports import IAIVisionClient

logger = logging.getLogger(__name__)

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"

SYSTEM_PROMPT = """
Ты — профессиональный эксперт-букинист и специалист по каталогизации книг для маркетплейса Ozon.
Твоя задача — изучить предоставленные фотографии книги (обложки, титульный лист, оборот, мантру/колофон, дефекты).
Верни ответ СТРОГО в формате валидного JSON со следующими полями:
{
  "title": "Точное название книги (без автора и подзаголовков)",
  "original_title": "Оригинальное название на иностранном языке (ТОЛЬКО для переводных книг, иначе '')",
  "author_cover": "Автор на обложке в естественном порядке Имя Фамилия (или 'не указан')",
  "author": "Полное ФИО автора в паспортном порядке Фамилия Имя Отчество (или 'не указан')",
  "publisher": "Наименование издательства БЕЗ слова 'издательство', 'изд-во' и кавычек",
  "brand": "Бренд издательства для Ozon (или 'Нет бренда')",
  "year": integer год выпуска,
  "series": "Название серии, если есть",
  "pages": integer точное количество страниц из колофона,
  "isbn": "ISBN с дефисами (если книга до 2011 года и не видна на фото со 100% четкостью — строго '')",
  "isbn_100_percent_on_photo": boolean,
  "barcode": "13 цифр EAN-13 без пробелов и дефисов, если есть",
  "cover_type": "Твердый переплет, Мягкая обложка, Тканевый переплет или Интегральный переплет",
  "condition": "Очень хорошая, Хорошая, Удовлетворительная или Плохая",
  "genre": "Литературное направление Ozon",
  "paper_type": "Типографская, Офсетная, Газетная, Картон или пустая строка",
  "age_limit": "0+, 6+, 12+, 16+, 18+ (только если прямо напечатано на фото, иначе '')",
  "annotation": "Емкое и литературное описание сюжета своими словами без дословных цитат",
  "translator": "ФИО переводчика в паспортном порядке (или '')",
  "illustrator": "ФИО иллюстратора сюжетных рисунков в паспортном порядке (НЕ художник обложки!)",
  "book_format_code": "Типографский формат из мантры (например: 60x90/16, 84x108/32, 70x100/16)",
  "width_mm": integer реальная ширина книги в мм,
  "length_mm": integer реальная длина (высота) книги в мм,
  "height_mm": integer толщина книги в мм,
  "weight_g": integer реальный вес книги в граммах
}
"""


def extract_json_safely(text: str) -> Dict[str, Any]:
    """Extract valid JSON from AI response, robust against markdown and thinking parts."""
    clean = text.strip()
    try:
        data = json.loads(clean)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Strip markdown fences
    clean_fence = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
    clean_fence = re.sub(r"\s*```$", "", clean_fence, flags=re.MULTILINE).strip()
    try:
        data = json.loads(clean_fence)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Search for outer braces
    m = re.search(r"(\{[\s\S]*\})", clean)
    if m:
        candidate = m.group(1).strip()
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            # Control character sanitization
            sanitized = re.sub(
                r"[\x00-\x1f]",
                lambda c: " " if c.group(0) not in "\r\n\t" else c.group(0),
                candidate,
            )
            data = json.loads(sanitized)
            if isinstance(data, dict):
                return data

    raise ExternalServiceError(f"Failed to extract valid JSON from Gemini output: {text[:200]}")


def preprocess_image(data: bytes, max_dim: int = 1200) -> bytes:
    """Resize image to max 1200px and normalize EXIF orientation to save bandwidth."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
            if max(img.width, img.height) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            return buf.getvalue()
    except Exception:
        # Gracefully return raw bytes if PIL cannot decode (e.g. mocked test payload)
        return data



def is_retryable_http_error(exception: BaseException) -> bool:
    """Predicate for tenacity retry: retry 429 and 503, never retry 400/401/403."""
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code in (429, 503)
    if isinstance(exception, httpx.TransportError):
        return True
    return False


class GeminiVisionClient(IAIVisionClient):
    """Gemini Vision AI client with model cascade, retry logic, and thinking-safe parsing."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        settings: Optional[AppSettings] = None,
        http_client: Optional[httpx.Client] = None,
        models: Optional[List[str]] = None,
        temperature: float = 0.1,
    ) -> None:
        self._settings = settings or AppSettings()
        self._api_key = api_key or self._settings.get_effective_gemini_key()
        self.models = models or self._settings.gemini_models or [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]
        self.temperature = temperature
        self._http_client = http_client or httpx.Client(timeout=45.0)

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def _require_api_key(self) -> str:
        if not self.is_configured:
            raise AuthenticationError("Gemini API key is not configured")
        return self._api_key.strip()

    @retry(
        retry=retry_if_exception(is_retryable_http_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _execute_request_with_retry(
        self, url: str, headers: Dict[str, str], payload: Dict[str, Any]
    ) -> httpx.Response:
        resp = self._http_client.post(url, headers=headers, json=payload)
        if resp.status_code == 400:
            error_data = resp.json().get("error", {})
            msg = error_data.get("message", "")
            if "API_KEY_INVALID" in msg or "API key not valid" in msg:
                raise AuthenticationError(f"Invalid Gemini API key: {msg}")
        resp.raise_for_status()
        return resp

    def _extract_text_content(self, candidate: Dict[str, Any]) -> str:
        """Extract text chunks safely skipping thinking thoughts."""
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        text_parts: List[str] = []
        for part in parts:
            if part.get("thought") is True:
                continue
            txt = part.get("text", "")
            if txt:
                text_parts.append(txt)
        return "\n".join(text_parts).strip()

    def _call_model(
        self, model: str, parts: List[Dict[str, Any]], key: str
    ) -> Dict[str, Any]:
        url = f"{GEMINI_API_ENDPOINT}/{model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        }
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": self.temperature,
            },
        }

        resp = self._execute_request_with_retry(url, headers, payload)
        res_data = resp.json()
        candidates = res_data.get("candidates", [])
        if not candidates:
            raise ExternalServiceError(f"Model {model} returned zero candidates: {res_data}")

        cand = candidates[0]
        finish_reason = cand.get("finishReason", "")

        # Recitation filter handling
        if finish_reason == "RECITATION":
            logger.warning("Recitation triggered on model %s. Retrying with paraphrase prompt.", model)
            retry_parts = parts + [
                {
                    "text": (
                        "ВНИМАНИЕ: Сработал фильтр recitation. Кратко перескажи сюжет и описание "
                        "книги своими словами в 1-2 предложениях без прямого цитирования текста на фото. "
                        "Верни валидный JSON со всеми полями."
                    )
                }
            ]
            retry_payload = {
                "contents": [{"parts": retry_parts}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": self.temperature + 0.1,
                },
            }
            resp_retry = self._execute_request_with_retry(url, headers, retry_payload)
            res_data = resp_retry.json()
            candidates = res_data.get("candidates", [])
            if not candidates:
                raise ExternalServiceError("Recitation retry returned zero candidates")
            cand = candidates[0]

        extracted_text = self._extract_text_content(cand)
        return extract_json_safely(extracted_text)

    def recognize_categorized(
        self, items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Recognize book metadata from categorized photo items with role annotations."""
        key = self._require_api_key()
        parts: List[Dict[str, Any]] = [{"text": SYSTEM_PROMPT}]

        for item in items:
            role_desc = item.get("role_name", "Фото книги")
            parts.append({"text": f"--- Категория фото: {role_desc} ---"})
            data = item.get("data")
            if not data and item.get("path"):
                try:
                    data = Path(item["path"]).read_bytes()
                except OSError:
                    continue
            if not data:
                continue

            optimized_data = preprocess_image(data)
            b64_str = base64.b64encode(optimized_data).decode("ascii")
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64_str,
                    }
                }
            )

        last_error: Optional[Exception] = None
        for model in self.models:
            try:
                logger.info("Attempting Gemini Vision with model: %s", model)
                return self._call_model(model, parts, key)
            except AuthenticationError:
                # Never cascade on invalid API key
                raise
            except Exception as e:
                logger.warning("Model %s failed: %s; trying next model in cascade", model, e)
                last_error = e

        raise ExternalServiceError(
            f"All models in Gemini cascade failed. Last error: {last_error}"
        )

    def recognize_images(self, image_paths: List[str]) -> Dict[str, Any]:
        """Implements IAIVisionClient protocol with standard image file paths."""
        items: List[Dict[str, Any]] = []
        for path in image_paths:
            p = Path(path)
            if p.is_file():
                items.append({"role_name": p.stem, "path": str(p)})
        return self.recognize_categorized(items)
