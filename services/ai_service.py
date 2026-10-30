"""
ai_service.py: Взаимодействие с Google Gemini Vision AI для каталогизации книг.
"""

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List

from core.constants import SYSTEM_PROMPT
from services.enrichment_service import calculate_dimensions_and_weight, parse_book_format_code


def extract_json_safely(text: str) -> Dict[str, Any]:
    """Надежное извлечение JSON из ответа Gemini Vision, устойчивое к markdown, комментариям и спецсимволам."""
    clean = text.strip()
    # 1. Прямой парсинг
    try:
        return json.loads(clean)
    except Exception:
        pass

    # 2. Очистка markdown fences ```json ... ```
    clean_fence = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
    clean_fence = re.sub(r"\s*```$", "", clean_fence, flags=re.MULTILINE).strip()
    try:
        return json.loads(clean_fence)
    except Exception:
        pass

    # 3. Поиск крайних фигурных скобок { ... }
    m = re.search(r"(\{[\s\S]*\})", clean)
    if m:
        candidate = m.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            # 4. Санитизация запрещенных контрольных символов внутри строк
            sanitized = re.sub(r"[\x00-\x1f]", lambda c: " " if c.group(0) not in "\r\n\t" else c.group(0), candidate)
            try:
                return json.loads(sanitized)
            except Exception:
                pass

    raise Exception(f"Не удалось извлечь валидный JSON из ответа ИИ: {text[:150]}...")


def sanitize_ai_book_data(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    По правилу пользователя: если ISBN не был распознан на 100% со страницы фото
    и книга до 2011 года (или советская), ISBN строго не указывается (пустая строка "").
    """
    if not isinstance(parsed, dict):
        return parsed

    year_val = None
    try:
        y_str = str(parsed.get("year") or "").strip()
        digits = re.findall(r"\d{4}", y_str)
        if digits:
            year_val = int(digits[0])
    except Exception:
        pass

    isbn_raw = str(parsed.get("isbn") or "").strip()
    is_100_percent = bool(parsed.get("isbn_100_percent_on_photo"))

    if year_val and year_val <= 2011:
        if not is_100_percent:
            parsed["isbn"] = ""
        elif year_val < 1987:
            # В СССР до 1987 года ISBN в принципе не существовал
            parsed["isbn"] = ""
        elif year_val <= 1991 and isbn_raw.startswith("978-"):
            # 13-значные 978- ISBN появились только в 2007 г., для СССР это галлюцинация
            parsed["isbn"] = ""
        elif isbn_raw in ["978-5-0000-0000-0", "000-0-0000-0000-0", "—", "-"]:
            parsed["isbn"] = ""

    # Санитизация возрастного ограничения (age_limit):
    # Указывается строго при 100% подтверждении на фото (без догадок и значений по умолчанию)
    age_raw = str(parsed.get("age_limit") or "").strip()
    if age_raw:
        if age_raw not in ["0+", "6+", "12+", "16+", "18+"]:
            m_age = re.search(r"\b(0|6|12|16|18)\s*\+", age_raw)
            age_raw = f"{m_age.group(1)}+" if m_age else ""
        # Для советских и букинистических книг до 2012 года маркировка 436-ФЗ (16+/18+) не существовала
        if year_val and year_val < 2012 and age_raw in ["16+", "18+"]:
            age_raw = ""
    parsed["age_limit"] = age_raw

    # Санитизация габаритов и массы книги
    try:
        pages_val = int(parsed.get("pages") or 200)
        cover_val = str(parsed.get("cover_type") or "Твердый переплет")
        paper_val = str(parsed.get("paper_type") or "Офсетная")
        fmt_val = str(parsed.get("book_format_code") or "").strip()
        w_in = parsed.get("width_mm")
        l_in = parsed.get("length_mm")

        cw, cl, ch, cwt = calculate_dimensions_and_weight(
            pages=pages_val,
            cover_type=cover_val,
            paper_type=paper_val,
            format_code=fmt_val,
            width_mm=w_in,
            length_mm=l_in
        )
        parsed["width_mm"] = cw
        parsed["length_mm"] = cl
        parsed["height_mm"] = ch
        parsed["weight_g"] = cwt
        print(f"[Sanitize] Габариты и масса рассчитаны физически: {cw}×{cl}×{ch} мм, {cwt} г ({fmt_val}, {pages_val} стр.)", flush=True)
    except Exception as e:
        print(f"[Sanitize] Ошибка санитизации габаритов: {e}", flush=True)

    return parsed


def call_gemini_vision(categorized_images: List[Dict[str, Any]], api_key: str) -> Dict[str, Any]:
    """
    Отправляет в Gemini Vision кадры с явными аннотациями ролей.
    categorized_images: список dict с 'role_name', 'mime', 'data'
    """
    parts = [{"text": SYSTEM_PROMPT}]

    for item in categorized_images:
        role_desc = item.get("role_name", "Фото книги")
        parts.append({"text": f"--- Категория фото: {role_desc} ---"})
        img_data = item.get("data") or ""
        # Очищаем data URL префикс, если присутствует (например: data:image/jpeg;base64,...)
        if img_data.startswith("data:") and "," in img_data:
            img_data = img_data.split(",", 1)[1]
        img_data = img_data.strip()

        mime = item.get("mime") or "image/jpeg"
        if not mime or mime == "image":
            mime = "image/jpeg"

        parts.append({
            "inline_data": {
                "mime_type": mime,
                "data": img_data
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }

    # Каскад сверхбыстрых и надежных моделей Gemini Vision
    models = [
        "gemini-3.5-flash-lite",    # ⚡ Легковесная и быстрая модель (~4-6 сек)
        "gemini-3.6-flash",         # Проверенная скоростная модель
        "gemini-3.1-flash-lite",    # Резервная модель
        "gemini-3-flash-preview",   # Флагманская модель
        "gemini-flash-lite-latest", # Альтернативный lite endpoint
    ]
    last_error = None

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if not candidates:
                    prompt_fb = res_data.get("promptFeedback", {})
                    raise Exception(f"Модель {model} не вернула кандидатов. promptFeedback={prompt_fb}")

                cand = candidates[0]
                finish_r = cand.get("finishReason", "UNKNOWN")
                content = cand.get("content", {})
                p_list = content.get("parts", [])

                # Защита от RECITATION (фильтр прямого цитирования авторских прав)
                if finish_r == "RECITATION" or not p_list or "text" not in p_list[0]:
                    if finish_r == "RECITATION":
                        print(f"[{model}] Сработал фильтр RECITATION. Выполняем быстрый пересказ без прямого цитирования...", flush=True)
                        retry_payload = {
                            "contents": [{
                                "parts": parts + [{
                                    "text": "ВНИМАНИЕ: Сработал фильтр recitation. Кратко перескажи сюжет и описание книги своими словами в 1-2 предложениях без прямого цитирования текста на фото. Верни валидный JSON со всеми полями."
                                }]
                            }],
                            "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"},
                            "safetySettings": payload["safetySettings"]
                        }
                        try:
                            req_retry = urllib.request.Request(
                                url,
                                data=json.dumps(retry_payload).encode("utf-8"),
                                headers={"Content-Type": "application/json"}
                            )
                            with urllib.request.urlopen(req_retry, timeout=30) as r_resp:
                                r_data = json.loads(r_resp.read().decode("utf-8"))
                                r_cands = r_data.get("candidates", [])
                                if r_cands:
                                    r_cand = r_cands[0]
                                    r_plist = r_cand.get("content", {}).get("parts", [])
                                    if r_plist and "text" in r_plist[0]:
                                        parsed = sanitize_ai_book_data(extract_json_safely(r_plist[0]["text"]))
                                        print(f"[{model}] Успешно распознано после авто-пересказа: «{parsed.get('title', '')}» (автор: {parsed.get('author_cover', '')}, ISBN: '{parsed.get('isbn', '')}')", flush=True)
                                        return parsed
                        except Exception as retry_e:
                            print(f"[{model}] Ошибка авто-пересказа: {retry_e}", flush=True)

                    raise Exception(f"Модель {model} вернула пустой ответ (finishReason={finish_r})")

                text_part = p_list[0]["text"]
                parsed = sanitize_ai_book_data(extract_json_safely(text_part))
                print(f"[{model}] Успешно распознано: «{parsed.get('title', '')}» (автор: {parsed.get('author_cover', '')}, ISBN: '{parsed.get('isbn', '')}')", flush=True)
                return parsed

        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            last_error = f"Ошибка Gemini API ({e.code}) [{model}]: {err_msg}"
            print(f"[{model}] HTTP {e.code}: {err_msg[:200]}", flush=True)
            if "API_KEY_INVALID" in err_msg or "API key not valid" in err_msg:
                raise Exception("Неверный API ключ Gemini! Проверьте ключ в настройках (кнопка в правом верхнем углу).")
            continue
        except Exception as e:
            last_error = str(e)
            print(f"[{model}] Ошибка: {e}", flush=True)
            continue

    raise Exception(last_error or "Не удалось получить ответ от Gemini API после перебора всех моделей")

