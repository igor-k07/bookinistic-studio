"""
enrichment_service.py: Сервис сверки и обогащения метаданных книг из внешних библиографических баз (FantLab, Open Library).
Работает как вторичный верификатор после распознавания Gemini Vision.
"""

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple


# Справочник стандартных типографских форматов советских и российских книг (доля листа -> Ш х Д в мм)
SOVIET_FORMAT_MAP = {
    # Большие / энциклопедические форматы
    "70x100/16": (176, 235), # 175-176 x 235-240 мм (детские книги, альбомы, энциклопедии)
    "70x90/16": (170, 215),  # Увеличенный широкий
    "70x108/16": (170, 260), # Академический
    "84x108/16": (205, 260), # Альбомный / подарочный
    # Увеличенные форматы
    "60x90/16": (145, 215),  # Самый частый увеличенный формат
    "60x84/16": (145, 200),  # Самый массовый стандарт советской книги
    # Стандартные форматы
    "84x108/32": (130, 200), # Типовой формат художественной литературы (130x205)
    # Малые / карманные форматы
    "70x108/32": (130, 165), # Малый стандарт
    "70x100/32": (120, 165), # Малый
    "70x90/32": (110, 165),  # Карманный стандарт
    "60x90/32": (107, 140),  # Карманный покетбук
    "60x84/32": (100, 140),  # Карманный малый
}


def parse_book_format_code(text: str) -> Optional[Tuple[str, int, int]]:
    """
    Распознает типографский формат из строки (например: '70x100 1/16', '60х90/16', '84*108/32', '145x215 мм').
    Возвращает кортеж (format_key, width_mm, length_mm) или None.
    """
    if not text:
        return None

    # 1. Сначала ищем долю печатного листа: число x число / доля (например, 84x108/32 или 70х100 1/16)
    m = re.search(r'(\d{2,3})\s*[xх*×]\s*(\d{2,3})\s*(?:(?:1/|/)\s*(\d{1,2}))', text, re.IGNORECASE)
    if m:
        w_sheet = m.group(1)
        l_sheet = m.group(2)
        fraction = m.group(3)
        key = f"{w_sheet}x{l_sheet}/{fraction}".lower()
        if key in SOVIET_FORMAT_MAP:
            w, l = SOVIET_FORMAT_MAP[key]
            return (key, w, l)
        rev_key = f"{l_sheet}x{w_sheet}/{fraction}".lower()
        if rev_key in SOVIET_FORMAT_MAP:
            w, l = SOVIET_FORMAT_MAP[rev_key]
            return (rev_key, w, l)

    # 2. Если доли листа нет, ищем явные миллиметры (например, '145x215 мм' или '176x235')
    m_mm = re.search(r'\(?(\d{2,3})\s*[xх*×]\s*(\d{2,3})\s*(?:мм)?\)?', text, re.IGNORECASE)
    if m_mm:
        d1 = int(m_mm.group(1))
        d2 = int(m_mm.group(2))
        if 80 <= d1 <= 400 and 80 <= d2 <= 400:
            w = min(d1, d2)
            l = max(d1, d2)
            return (f"{w}x{l}mm", w, l)
    return None


def calculate_dimensions_and_weight(
    pages: int,
    cover_type: str = "Твердый переплет",
    paper_type: str = "Офсетная",
    format_code: str = "",
    width_mm: Optional[int] = None,
    length_mm: Optional[int] = None
) -> Tuple[int, int, int, int]:
    """
    Рассчитывает точные физические габариты и чистую массу книги:
    Возвращает (width_mm, length_mm, height_mm, weight_g).
    """
    w = width_mm
    l = length_mm
    if format_code:
        fmt_res = parse_book_format_code(format_code)
        if fmt_res:
            _, fw, fl = fmt_res
            if not w or w <= 50:
                w = fw
            if not l or l <= 50:
                l = fl

    w = int(w or 130)
    l = int(l or 205)
    if w > l:
        w, l = l, w

    p = max(8, int(pages or 150))
    cover_low = str(cover_type or "Твердый").lower()
    is_hard = any(k in cover_low for k in ["тверд", "интегральн", "бумвинил", "кож", "тканев"])

    paper_low = str(paper_type or "Офсетная").lower()
    if "мелован" in paper_low:
        p_dens = 115
    elif "газетн" in paper_low:
        p_dens = 50
    elif "типограф" in paper_low or "пухл" in paper_low:
        p_dens = 65
    else:
        p_dens = 80 # Стандартная офсетная бумага

    area_m2 = (w / 1000.0) * (l / 1000.0)
    sheets = p / 2.0
    block_wt = sheets * area_m2 * p_dens

    if is_hard:
        # 2 сторонки переплетного картона ~1200 г/м² + 2 форзаца (~120 г/м²) + покровный материал/клей ~20г
        cover_wt = 2 * area_m2 * 1200 + 4 * area_m2 * 120 + 20
        # Толщина корешка: блок (0.048 мм на страницу) + 3.5 мм картон
        spine = max(8, round(p * 0.048 + 3.5))
    else:
        # Мягкая обложка: картон 250 г/м²
        cover_wt = 2 * area_m2 * 250 + 5
        spine = max(4, round(p * 0.048 + 1.0))

    total_wt = max(50, round(block_wt + cover_wt))
    return w, l, spine, total_wt


def _clean_query(text: str) -> str:
    """Очищает строку запроса от кавычек, скобок и пунктуации."""
    return re.sub(r"[\"«».,!?;:()\[\]]", " ", text).strip()


def search_fantlab_edition(
    title: str,
    author: str = "",
    year: Optional[int] = None,
    publisher: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Поиск издания в базе FantLab по названию, автору и году.
    Возвращает dict с метаданными лучшего совпадения.
    """
    clean_t = _clean_query(title)
    if not clean_t:
        return None

    clean_a = _clean_query(author)
    q_str = f"{clean_a} {clean_t}".strip()
    q_enc = urllib.parse.quote(q_str)
    url = f"https://api.fantlab.ru/search-editions?q={q_enc}"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            matches = data.get("matches", [])
            if not matches:
                return None

            # 1. Приоритет: совпадение по точному году
            if year:
                try:
                    y_int = int(year)
                    exact_year = [m for m in matches if m.get("year") == y_int]
                    if exact_year:
                        if publisher:
                            pub_low = publisher.lower()
                            pub_match = [m for m in exact_year if pub_low in (m.get("publisher") or "").lower()]
                            if pub_match:
                                return pub_match[0]
                        return exact_year[0]
                except Exception:
                    pass

            # 2. Приоритет: совпадение по издательству
            if publisher:
                pub_low = publisher.lower()
                exact_pub = [m for m in matches if pub_low in (m.get("publisher") or "").lower()]
                if exact_pub:
                    return exact_pub[0]

            # 3. Дефолт: первое релевантное совпадение
            return matches[0]

    except Exception as e:
        print(f"[Enrichment:FantLab] Ошибка поиска издания: {e}", flush=True)
        return None


def get_fantlab_artist_fullname(art_id: int) -> Optional[str]:
    """
    Извлекает официальное полное ФИО художника по его ID в FantLab (/art{id}).
    Приводит к официальному паспортному порядку Ozon: 'Фамилия Имя Отчество'.
    """
    url = f"https://fantlab.ru/art{art_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            m = re.search(r"<h1[^>]*>Художник\s*(?:&mdash;|-)\s*([^<]+)</h1>", html)
            if m:
                raw_name = m.group(1).strip()
                parts = raw_name.split()
                if len(parts) == 3:
                    # Имя Отчество Фамилия -> Фамилия Имя Отчество
                    return f"{parts[2]} {parts[0]} {parts[1]}"
                elif len(parts) == 2:
                    # Имя Фамилия -> Фамилия Имя
                    return f"{parts[1]} {parts[0]}"
                return raw_name
    except Exception as e:
        print(f"[Enrichment:FantLab] Ошибка получения ФИО художника art{art_id}: {e}", flush=True)
    return None


def get_fantlab_edition_details(edition_id: int) -> Optional[Dict[str, Any]]:
    """Получает детальную карточку издания по edition_id."""
    url = f"https://api.fantlab.ru/edition/{edition_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"[Enrichment:FantLab] Ошибка получения карточки edition/{edition_id}: {e}", flush=True)
        return None


def get_original_title_openlibrary(author: str, title: str) -> Optional[str]:
    """Поиск оригинального названия произведения на латинице в Open Library."""
    clean_a = _clean_query(author)
    clean_t = _clean_query(title)
    if not clean_t:
        return None

    q_str = f"{clean_a} {clean_t}".strip()
    q_enc = urllib.parse.quote(q_str)
    url = f"https://openlibrary.org/search.json?q={q_enc}&limit=3"

    req = urllib.request.Request(url, headers={"User-Agent": "BookinisticStudio/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            docs = data.get("docs", [])
            for doc in docs:
                t = doc.get("title")
                # Ищем латинское оригинальное название
                if t and any("a" <= c.lower() <= "z" for c in t):
                    return t
    except Exception as e:
        print(f"[Enrichment:OpenLibrary] Ошибка поиска: {e}", flush=True)
    return None


def enrich_book_metadata(data: Dict[str, Any], has_illustrations: bool = True) -> Dict[str, Any]:
    """
    Основная функция сверки и обогащения данных книги:
    1. Ищет точное совпадение в FantLab.
    2. Расшифровывает инициалы художника-иллюстратора в полное паспортное ФИО Ozon.
    3. Подтягивает латинское название книги (original_title) для зарубежных переводов.
    4. Уточняет точное количество страниц и размеры в мм, если они отсутствовали.
    5. Гарантирует правило: если иллюстраций нет в пуле — поле illustrator всегда пустая строка.
    """
    if not isinstance(data, dict):
        return data

    title = str(data.get("title") or "").strip()
    author = str(data.get("author") or data.get("author_cover") or "").strip()
    year = data.get("year")
    publisher = str(data.get("publisher") or "").strip()

    # Если в пуле фото нет кадров со слотом иллюстраций — иллюстратора строго обнуляем
    if not has_illustrations:
        data["illustrator"] = ""

    # Проверяем, есть ли признаки сложной книги, требующей сверки:
    curr_ill = str(data.get("illustrator") or "").strip()
    curr_orig = str(data.get("original_title") or "").strip()
    curr_pages = data.get("pages")

    # Инициалы у иллюстратора (например: 'Васильева В.', 'В. Васнецов', 'И. Билибин')
    has_abbreviated_artist = bool(
        curr_ill and (
            re.search(r"\b[А-ЯЁ]\.?\s*$", curr_ill) or
            re.search(r"^[А-ЯЁ]\.?\s+", curr_ill) or
            len(curr_ill.split()) < 3
        )
    )

    # Пробуем найти книгу в FantLab
    fl_match = search_fantlab_edition(title, author, year, publisher)
    if fl_match:
        ed_id = fl_match.get("edition_id")
        data["verified_by"] = f"FantLab #{ed_id}"
        print(f"✨ [Enrichment] Найдено совпадение в FantLab: ID #{ed_id} «{fl_match.get('name')}» ({fl_match.get('year')} г.)", flush=True)

        details = get_fantlab_edition_details(ed_id) if ed_id else None
        if details:
            # 1. Расшифровка художника-иллюстратора
            if has_illustrations:
                desc = details.get("description") or ""
                art_m = re.search(r'/art(\d+)', desc)
                if art_m:
                    art_id = int(art_m.group(1))
                    full_artist_name = get_fantlab_artist_fullname(art_id)
                    if full_artist_name:
                        print(f"🎨 [Enrichment] Иллюстратор расшифрован из базы: '{curr_ill}' -> '{full_artist_name}'", flush=True)
                        data["illustrator"] = full_artist_name

            # 2. Уточнение точного числа страниц
            fl_pages = details.get("pages")
            if fl_pages:
                try:
                    p_int = int(fl_pages)
                    if p_int > 0:
                        data["pages"] = p_int
                except Exception:
                    pass

            # 3. Извлечение точных размеров книги в мм из FantLab
            found_dims = False
            fl_fmt_mm = details.get("format_mm") or ""
            if fl_fmt_mm and "x" in fl_fmt_mm.lower():
                try:
                    f_parts = re.split(r"[xхXХ]", str(fl_fmt_mm).strip())
                    if len(f_parts) == 2:
                        d1 = int(f_parts[0].strip())
                        d2 = int(f_parts[1].strip())
                        if d1 > 50 and d2 > 50:
                            data["width_mm"] = min(d1, d2)
                            data["length_mm"] = max(d1, d2)
                            found_dims = True
                            print(f"📏 [Enrichment] Точные габариты из FantLab (format_mm): {data['width_mm']} × {data['length_mm']} мм", flush=True)
                except Exception:
                    pass

            # Если format_mm не заполнен, проверяем типографский формат издания (например: '60x84/16')
            fl_fmt_code = str(details.get("format") or "").strip()
            if fl_fmt_code:
                data["book_format_code"] = fl_fmt_code
                if not found_dims:
                    parsed_fmt = parse_book_format_code(fl_fmt_code)
                    if parsed_fmt:
                        _, w_sov, l_sov = parsed_fmt
                        data["width_mm"] = w_sov
                        data["length_mm"] = l_sov
                        found_dims = True
                        print(f"📏 [Enrichment] Габариты определены по формату листа '{fl_fmt_code}': {w_sov} × {l_sov} мм", flush=True)

            # 4. Уточнение серии, если не была распознана
            fl_series = fl_match.get("series")
            if fl_series and not data.get("series"):
                data["series"] = fl_series

    # 5. Обогащение оригинального названия через Open Library (если книга переводная и латиницы нет)
    if not curr_orig:
        # Проверяем, похож ли автор на иностранного
        author_low = author.lower()
        is_foreign = any(name in author_low for name in [
            "линдгрен", "рид", "верн", "твен", "лондон", "дюма", "толкин", "толкиен",
            "конан дойл", "кристи", "по", "уэллс", "киплинг", "азимов", "лем",
            "диккенс", "скотт", "вайльд", "уайльд", "свифт", "дефо", "хаггард", "брэдбери"
        ])
        if is_foreign:
            ol_title = get_original_title_openlibrary(author, title)
            if ol_title:
                print(f"🌍 [Enrichment] Оригинальное название найдено в Open Library: '{ol_title}'", flush=True)
                data["original_title"] = ol_title

    # 6. Физический точный расчет габаритов и массы книги
    try:
        pages_val = data.get("pages") or 200
        cover_val = data.get("cover_type") or "Твердый переплет"
        paper_val = data.get("paper_type") or "Офсетная"
        fmt_val = data.get("book_format_code") or ""
        w_in = data.get("width_mm")
        l_in = data.get("length_mm")
        cw, cl, ch, cwt = calculate_dimensions_and_weight(
            pages=pages_val,
            cover_type=cover_val,
            paper_type=paper_val,
            format_code=fmt_val,
            width_mm=w_in,
            length_mm=l_in
        )
        data["width_mm"] = cw
        data["length_mm"] = cl
        data["height_mm"] = ch
        data["weight_g"] = cwt
        print(f"⚖️ [Enrichment] Физические замеры рассчитаны: {cw} × {cl} × {ch} мм, вес {cwt} г", flush=True)
    except Exception as e:
        print(f"[Enrichment] Ошибка расчета габаритов: {e}", flush=True)

    # Финальная гарантия по иллюстратору
    if not has_illustrations:
        data["illustrator"] = ""

    return data

