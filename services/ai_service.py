"""
ai_service.py: Взаимодействие с Google Gemini Vision AI для каталогизации книг.
"""

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List

from core.constants import OZON_PAPERS, SYSTEM_PROMPT, normalize_genre
from services.db_service import reconcile_with_references
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

    # По правилу пользователя: целевая аудитория исключена (строго пустая строка)
    parsed["target_audience"] = ""

    # По правилу пользователя: цена никогда не генерируется ИИ (строго пустая строка под ручной ввод)
    parsed["price"] = ""
    parsed["suggested_price"] = ""

    # Санитизация автора: если ИИ не уверен на 100% или автор отсутствует — строго пустая строка
    for a_field in ("author", "author_cover"):
        a_val = str(parsed.get(a_field) or "").strip()
        if a_val.lower() in ("не указан", "нет автора", "none", "null", "—", "-"):
            parsed[a_field] = ""
        else:
            parsed[a_field] = a_val

    # Санитизация типа бумаги: строго одно из 12 значений Ozon, иначе пустая строка под ручной выбор
    paper_raw = str(parsed.get("paper_type") or "").strip()
    if paper_raw not in OZON_PAPERS:
        parsed["paper_type"] = ""
    else:
        parsed["paper_type"] = paper_raw

    # Санитизация направления/жанра Ozon: исключаем несуществующий жанр 'Детская литература'
    raw_genre = str(parsed.get("genre") or "").strip()
    parsed["genre"] = normalize_genre(raw_genre, str(parsed.get("title") or ""), str(parsed.get("annotation") or ""))

    # Санитизация аннотации: убираем любые случайные предупреждения или дисклеймеры от ИИ
    if parsed.get("annotation"):
        ant = str(parsed["annotation"]).strip()
        warning_str = "ВНИМАНИЕ! КНИГА НЕ НОВАЯ. Имеются определённые нюансы (повреждения) см. дополнительные фото."
        if warning_str in ant:
            ant = ant.replace(warning_str, "").strip()
        clean_marker_list = [
            "\n\nСохранность / Дефекты:", "\n\nСохранность:", "\n\nДефекты:",
            "\nСохранность / Дефекты:", "\nСохранность:", "\nДефекты:"
        ]
        for m in clean_marker_list:
            if m in ant:
                ant = ant.split(m)[0].strip()
        while ant.startswith("\n"):
            ant = ant.lstrip("\n").strip()
        parsed["annotation"] = ant

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

    # Интеллектуальная сверка и канонизация по накопленной базе магазина catalog.db
    try:
        parsed = reconcile_with_references(parsed)
    except Exception as e:
        print(f"[Sanitize] Ошибка сверки с базой catalog.db: {e}", flush=True)

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
        from services.vault_service import resolve_photo_bytes
        img_bytes = resolve_photo_bytes(item)
        if not img_bytes:
            continue
        img_data = base64.b64encode(img_bytes).decode("ascii")

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


def classify_and_group_book_photos(photos: List[Dict[str, Any]], api_key: str) -> List[Dict[str, Any]]:
    """
    Интеллектуальная ИИ-классификация пачки фотографий:
    1. Находит границы книг (каждая новая книга обычно начинается с Лицевой обложки).
    2. Присваивает роль каждому кадру:
       - 'cover_front': Лицевая обложка
       - 'cover_back': Оборот переплета / штрихкод
       - 'info_pages': Титульный лист, оборот титула, форзац с выходными данными (может быть несколько!)
       - 'illustrations': Иллюстрации, гравюры, цветные вклейки (может быть несколько или 0)
       - 'mantra_defects': Дефекты, повреждения, пятна, пометки (может быть несколько или 0)
    Возвращает список классифицированных кадров с полями 'index', 'book_num', 'role'.
    """
    import io
    from PIL import Image

    if not photos:
        return []

    parts = [{
        "text": (
            "Ты эксперт-букинист и каталогизатор антикварных и советских книг для маркетплейса.\n"
            "Перед тобой упорядоченная последовательность фотографий одной или нескольких книг.\n"
            "Твоя задача:\n"
            "1. Понять, сколько здесь разных книг и где границы каждой книги (каждая новая книга начинается с лицевой обложки 'cover_front').\n"
            "2. Для каждого кадра определить его точную роль в книге:\n"
            "   - 'cover_front': Лицевая сторона переплета / обложки книги (ровно 1 на книгу)\n"
            "   - 'cover_back': Задняя сторона переплета / задник со штрихкодом (1 на книгу или несколько для комплектов)\n"
            "   - 'info_pages': Титульный лист, оборот титула, форзац с выходными данными, колофон (может быть несколько кадров!)\n"
            "   - 'illustrations': Художественные иллюстрации, цветные вкладки, гравюры, карты, развороты (может быть несколько или 0)\n"
            "   - 'mantra_defects': Фото повреждений: надрывы, лисьи пятна, пометки, штампы, сбитые углы (может быть несколько или 0)\n\n"
            "Верни строгий JSON в формате:\n"
            "{\n"
            '  "items": [\n'
            '    {"index": 0, "book_num": 1, "role": "cover_front"},\n'
            '    {"index": 1, "book_num": 1, "role": "cover_back"},\n'
            '    {"index": 2, "book_num": 1, "role": "info_pages"},\n'
            '    {"index": 3, "book_num": 1, "role": "info_pages"},\n'
            '    {"index": 4, "book_num": 2, "role": "cover_front"}\n'
            "  ]\n"
            "}"
        )
    }]

    for idx, item in enumerate(photos):
        from services.vault_service import resolve_photo_bytes
        img_b = resolve_photo_bytes(item)
        if not img_b:
            continue

        # Создаем сверхкомпактный thumbnail (до 300px), чтобы запрос летал за 1-2 секунды
        try:
            im = Image.open(io.BytesIO(img_b))
            im.thumbnail((300, 300))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=68)
            thumb_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            thumb_b64 = base64.b64encode(img_b).decode("ascii")

        parts.append({"text": f"--- Фото #{idx} ---"})
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": thumb_b64
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0
        }
    }

    models = [
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-2.5-pro"
    ]

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=18) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                cands = res_data.get("candidates", [])
                if cands:
                    t = cands[0]["content"]["parts"][0]["text"]
                    parsed = extract_json_safely(t)
                    items = parsed.get("items", [])
                    if isinstance(items, list) and items:
                        print(f"[{model}] Успешно классифицирована пачка из {len(items)} фото!", flush=True)
                        return items
        except Exception as e:
            print(f"[classify_and_group] Ошибка модели {model}: {e}", flush=True)
            continue

    # Fallback если ИИ недоступен
    fallback = []
    for i in range(len(photos)):
        role = "cover_front" if i == 0 else ("cover_back" if i == 1 else "info_pages")
        fallback.append({"index": i, "book_num": 1, "role": role})
    return fallback

