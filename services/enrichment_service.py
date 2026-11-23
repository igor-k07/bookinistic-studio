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
    return re.sub(r"[\"«».,!?;:()\[\]]", " ", text or "").strip()


def _normalize_isbn(isbn_str: Optional[str]) -> str:
    """Очищает ISBN, оставляя только цифры и X."""
    if not isbn_str:
        return ""
    return re.sub(r"[^\dX]", "", str(isbn_str).upper())


def _isbns_match(isbn1: Optional[str], isbn2: Optional[str]) -> bool:
    """Сверяет два ISBN с учетом дефисов, пробелов и формата ISBN-10 / ISBN-13."""
    c1 = _normalize_isbn(isbn1)
    c2 = _normalize_isbn(isbn2)
    if not c1 or not c2:
        return False
    if c1 == c2:
        return True
    if len(c1) == 13 and len(c2) == 10 and c1.startswith("978"):
        return c1[3:12] == c2[:9]
    if len(c2) == 13 and len(c1) == 10 and c2.startswith("978"):
        return c2[3:12] == c1[:9]
    return False


def get_fantlab_work_original_title(work_id: int) -> Optional[str]:
    """Получает оригинальное иностранное название произведения по work_id из FantLab."""
    url = f"https://api.fantlab.ru/work/{work_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            orig = (data.get("work_name_orig") or "").strip()
            if orig and any("a" <= c.lower() <= "z" for c in orig):
                return orig
    except Exception as e:
        print(f"[Enrichment:FantLab] Ошибка получения work/{work_id}: {e}", flush=True)
    return None


def search_fantlab_edition(
    title: str = "",
    author: str = "",
    year: Optional[int] = None,
    publisher: Optional[str] = None,
    isbn: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Поиск издания в базе FantLab.
    1. Если указан ISBN — в первую очередь ищет прямое совпадение по ISBN.
    2. Если по ISBN не найдено или ISBN не указан — ищет по автору и названию.
    Возвращает (match_dict, is_exact_isbn_match).
    """
    clean_isbn = _normalize_isbn(isbn)

    # 1. Поиск напрямую по ISBN
    if clean_isbn:
        queries = [isbn.strip(), clean_isbn]
        if len(clean_isbn) == 13 and clean_isbn.startswith("978"):
            queries.append(clean_isbn[3:12])

        for q_cand in queries:
            if not q_cand:
                continue
            q_enc = urllib.parse.quote(q_cand)
            url = f"https://api.fantlab.ru/search-editions?q={q_enc}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            try:
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    d = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    matches = d.get("matches", [])
                    for m in matches:
                        if _isbns_match(m.get("isbn"), isbn):
                            return m, True
                        ed_id = m.get("edition_id")
                        if ed_id:
                            det = get_fantlab_edition_details(ed_id)
                            if det:
                                for det_isbn in det.get("isbns", []):
                                    if _isbns_match(det_isbn, isbn):
                                        m["_cached_details"] = det
                                        return m, True
            except Exception as e:
                print(f"[Enrichment:FantLab] Ошибка поиска по ISBN '{q_cand}': {e}", flush=True)

    # 2. Поиск по названию и автору
    clean_t = _clean_query(title)
    clean_a = _clean_query(author)
    if not clean_t and not clean_a:
        return None, False

    q_str = f"{clean_a} {clean_t}".strip()
    q_enc = urllib.parse.quote(q_str)
    url = f"https://api.fantlab.ru/search-editions?q={q_enc}"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            matches = data.get("matches", [])
            if not matches:
                return None, False

            # Если пользователь передавал ISBN, проверяем среди результатов на точное совпадение
            if clean_isbn:
                for m in matches:
                    if _isbns_match(m.get("isbn"), isbn):
                        return m, True
                    ed_id = m.get("edition_id")
                    if ed_id:
                        det = get_fantlab_edition_details(ed_id)
                        if det:
                            for det_isbn in det.get("isbns", []):
                                if _isbns_match(det_isbn, isbn):
                                    m["_cached_details"] = det
                                    return m, True

            # Иначе: фильтрация по году
            if year:
                try:
                    y_int = int(year)
                    exact_year = [m for m in matches if m.get("year") == y_int]
                    if exact_year:
                        if publisher:
                            pub_low = publisher.lower()
                            pub_match = [m for m in exact_year if pub_low in (m.get("publisher") or "").lower()]
                            if pub_match:
                                return pub_match[0], False
                        return exact_year[0], False
                except Exception:
                    pass

            # Фильтрация по издательству
            if publisher:
                pub_low = publisher.lower()
                exact_pub = [m for m in matches if pub_low in (m.get("publisher") or "").lower()]
                if exact_pub:
                    return exact_pub[0], False

            # Первое релевантное совпадение
            return matches[0], False

    except Exception as e:
        print(f"[Enrichment:FantLab] Ошибка поиска издания: {e}", flush=True)
        return None, False


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


def _clean_fantlab_text(text: Optional[str]) -> str:
    """Очищает bb-code теги FantLab вида [autor=19]...[/autor], [pub=33]...[/pub], [b]...[/b] и html."""
    if not text:
        return ""
    cleaned = re.sub(r"\[/?[a-zA-Z]+(?:=[^\]]*)?\]", "", str(text))
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return cleaned.strip()


def _map_cover_type(fl_cover: Optional[str]) -> str:
    """Приводит тип обложки FantLab к справочнику Ozon."""
    if not fl_cover:
        return "Твердый переплет"
    c = fl_cover.lower()
    if "супер" in c:
        if "мягк" in c:
            return "Мягкая обложка, суперобложка"
        elif "интеграл" in c:
            return "Интегральный переплет, суперобложка"
        elif "ткан" in c:
            return "Тканевый переплет, суперобложка"
        return "Твердый переплет, суперобложка"
    if "мягк" in c or "обложк" in c:
        if "клапан" in c:
            return "Обложка с клапанами"
        return "Мягкая обложка"
    elif "интеграл" in c:
        return "Интегральный переплет"
    elif "ткан" in c:
        return "Тканевый переплет"
    elif "кож" in c:
        return "Кожаный переплет"
    return "Твердый переплет"


def _detect_paper_type(text: str) -> Optional[str]:
    """Определяет тип бумаги из примечаний и описания издания."""
    if not text:
        return None
    t = text.lower()
    if "мелован" in t:
        if "глянц" in t:
            return "Мелованная глянцевая"
        return "Мелованная матовая"
    if "офсет" in t:
        return "Офсетная"
    if "газетн" in t:
        return "Газетная"
    if "типографск" in t:
        return "Типографская"
    if "пухл" in t:
        return "Пухлая"
    return None


def _extract_translator(text: str) -> Optional[str]:
    """Извлекает имя переводчика из текста описания/примечаний FantLab."""
    if not text:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\[/?[a-zA-Z]+(?:=[^\]]*)?\]", " ", cleaned)
    m = re.search(r"(?:перевод(?:чик(?:а)?)?(?:\s+с\s+[а-яё]+(?:ского)?)?|в\s+переводе)[\s:]+([А-ЯЁ][^\n\r,;/]+)", cleaned, re.IGNORECASE)
    if m:
        words = m.group(1).split()
        chosen = []
        for w in words[:3]:
            w_clean = re.sub(r"[;,.]+$", "", w).strip()
            if not w_clean or re.match(r"(?:иллюстрац|серия|художн|подписан|тираж|отв|ред)", w_clean, re.I):
                break
            chosen.append(w.rstrip(",;"))
        if chosen:
            res = " ".join(chosen).rstrip(".")
            if any(c.isupper() for c in res):
                return res
    return None


def enrich_book_metadata(
    data: Dict[str, Any],
    has_illustrations: bool = True,
    skip_dimensions: bool = False
) -> Dict[str, Any]:
    """
    Основная функция сверки и обогащения данных книги:
    1. Ищет точное совпадение в FantLab по ISBN (в первую очередь) или названию/автору.
    2. При точном совпадении ISBN (exact_isbn_match=True):
       - Уточняет поля книги (title, author, publisher, year, series, pages, cover_type,
         book_format_code, isbn, original_title, translator, paper_type).
       - Строго НЕ перезаписывает price, annotation и размеры, если skip_dimensions=True.
    3. При неточном совпадении (по названию/автору):
       - Безопасно дополняет только недостающие поля (pages, series, format, etc.).
    4. Расшифровывает инициалы художника-иллюстратора в полное паспортное ФИО Ozon,
       но только если в слоте иллюстраций есть реальные фото (has_illustrations=True).
    5. Если skip_dimensions=False — рассчитывает физические размеры и массу книги.
    """
    if not isinstance(data, dict):
        return data

    res = dict(data)
    title = str(res.get("title") or "").strip()
    author = str(res.get("author") or res.get("author_cover") or "").strip()
    year = res.get("year")
    publisher = str(res.get("publisher") or "").strip()
    isbn = str(res.get("isbn") or "").strip()

    # Если в пуле фото нет кадров со слотом иллюстраций — иллюстратора строго обнуляем
    if not has_illustrations:
        res["illustrator"] = ""

    curr_ill = str(res.get("illustrator") or "").strip()

    # Поиск книги в базе FantLab
    fl_match, is_exact_isbn = search_fantlab_edition(title, author, year, publisher, isbn)
    res["exact_isbn_match"] = is_exact_isbn

    if fl_match:
        ed_id = fl_match.get("edition_id")
        details = fl_match.get("_cached_details") or (get_fantlab_edition_details(ed_id) if ed_id else {}) or {}

        if is_exact_isbn:
            # 100% точное совпадение по ISBN -> уточняем карточку книги из официальной базы
            res["verified_by"] = f"FantLab (ISBN {fl_match.get('isbn') or isbn})"
            print(f"🎯 [Enrichment] 100% совпадение по ISBN: уточняем карточку #{ed_id} «{fl_match.get('name')}»", flush=True)

            # Название
            fl_title = (details.get("edition_name") or fl_match.get("name") or "").strip()
            if fl_title:
                res["title"] = fl_title

            # Авторы
            creators = details.get("creators") or {}
            authors_list = creators.get("authors") if isinstance(creators, dict) else None
            if authors_list and isinstance(authors_list, list):
                fl_author = ", ".join(a["name"].strip() for a in authors_list if isinstance(a, dict) and a.get("name"))
            else:
                fl_author = _clean_fantlab_text(fl_match.get("autors"))
            if fl_author:
                res["author"] = fl_author
                res["author_cover"] = fl_author

            # Издательство и бренд
            publishers_list = creators.get("publishers") if isinstance(creators, dict) else None
            if publishers_list and isinstance(publishers_list, list):
                fl_pub = ", ".join(p["name"].strip() for p in publishers_list if isinstance(p, dict) and p.get("name"))
            else:
                fl_pub = _clean_fantlab_text(fl_match.get("publisher"))
            if fl_pub:
                from core.domain.rules import clean_publisher_name
                fl_pub = clean_publisher_name(fl_pub)
                res["publisher"] = fl_pub
                try:
                    from services.db_service import get_catalog_references, _match_brand_from_publisher
                    refs = get_catalog_references()
                    res["brand"] = _match_brand_from_publisher(fl_pub, refs.get("brands", []))
                except Exception:
                    res["brand"] = fl_pub

            # Год издания
            fl_year = fl_match.get("year") or details.get("year")
            if fl_year:
                try:
                    res["year"] = int(fl_year)
                except Exception:
                    pass

            # Серия
            series_list = details.get("series") if isinstance(details.get("series"), list) else None
            if series_list and isinstance(series_list, list):
                fl_series = ", ".join(s["name"].strip() for s in series_list if isinstance(s, dict) and s.get("name"))
            else:
                fl_series = _clean_fantlab_text(fl_match.get("series"))
            if fl_series:
                res["series"] = fl_series

            # Страницы
            fl_pages = details.get("pages")
            if fl_pages:
                try:
                    p_int = int(fl_pages)
                    if p_int > 0:
                        res["pages"] = p_int
                except Exception:
                    pass

            # Переплет
            fl_cover = details.get("cover_type")
            if fl_cover:
                res["cover_type"] = _map_cover_type(fl_cover)

            # Формат книги
            fl_fmt_code = str(details.get("format") or "").strip()
            if fl_fmt_code:
                res["book_format_code"] = fl_fmt_code

            # Нормализованный ISBN издания
            fl_isbns = details.get("isbns") or []
            fl_isbn_best = fl_match.get("isbn") or (fl_isbns[0] if fl_isbns else isbn)
            if fl_isbn_best:
                res["isbn"] = fl_isbn_best

            # Примечания и описание издания
            notes_and_desc = f"{details.get('notes') or ''} {details.get('description') or ''} {fl_match.get('notes') or ''}".strip()

            # Переводчик
            fl_trans = _extract_translator(notes_and_desc)
            if fl_trans:
                res["translator"] = fl_trans

            # Тип бумаги
            fl_paper = _detect_paper_type(notes_and_desc)
            if fl_paper:
                res["paper_type"] = fl_paper

            # Оригинальное название иностранного произведения
            desc_text = details.get("description") or ""
            work_ids = re.findall(r"/work(\d+)", desc_text)
            orig_found = False
            for w_id in work_ids:
                orig_work = get_fantlab_work_original_title(int(w_id))
                if orig_work:
                    res["original_title"] = orig_work
                    orig_found = True
                    break
            if not orig_found and not res.get("original_title"):
                ol_title = get_original_title_openlibrary(res.get("author", author), res.get("title", title))
                if ol_title:
                    res["original_title"] = ol_title

        else:
            # Не точное совпадение по ISBN -> деликатное дополнение только недостающих полей
            res["verified_by"] = f"FantLab #{ed_id}"
            print(f"✨ [Enrichment] Частичное совпадение в FantLab: #{ed_id} «{fl_match.get('name')}» ({fl_match.get('year')} г.)", flush=True)

            fl_pages = details.get("pages")
            if fl_pages and not res.get("pages"):
                try:
                    p_int = int(fl_pages)
                    if p_int > 0:
                        res["pages"] = p_int
                except Exception:
                    pass

            fl_series = fl_match.get("series")
            if fl_series and not res.get("series"):
                res["series"] = _clean_fantlab_text(fl_series)

            fl_fmt_code = str(details.get("format") or "").strip()
            if fl_fmt_code and not res.get("book_format_code"):
                res["book_format_code"] = fl_fmt_code

        # Для обоих случаев: расшифровка иллюстратора (только если иллюстрации присутствуют!)
        if has_illustrations:
            desc = details.get("description") or ""
            art_m = re.search(r'/art(\d+)', desc)
            if art_m:
                art_id = int(art_m.group(1))
                full_artist_name = get_fantlab_artist_fullname(art_id)
                if full_artist_name:
                    print(f"🎨 [Enrichment] Иллюстратор расшифрован из базы: '{curr_ill}' -> '{full_artist_name}'", flush=True)
                    res["illustrator"] = full_artist_name
        else:
            res["illustrator"] = ""

        # Габариты из базы FantLab (если format_mm указан)
        fl_fmt_mm = details.get("format_mm") or ""
        if fl_fmt_mm and "x" in fl_fmt_mm.lower():
            try:
                f_parts = re.split(r"[xхXХ]", str(fl_fmt_mm).strip())
                if len(f_parts) == 2:
                    d1 = int(f_parts[0].strip())
                    d2 = int(f_parts[1].strip())
                    if d1 > 50 and d2 > 50:
                        res["width_mm"] = min(d1, d2)
                        res["length_mm"] = max(d1, d2)
            except Exception:
                pass

        if not res.get("width_mm") and res.get("book_format_code"):
            parsed_fmt = parse_book_format_code(res["book_format_code"])
            if parsed_fmt:
                _, w_sov, l_sov = parsed_fmt
                res["width_mm"] = w_sov
                res["length_mm"] = l_sov

    # Если оригинальное название еще не заполнено и автор иностранный
    if not res.get("original_title"):
        author_check = (res.get("author") or author).lower()
        is_foreign = any(name in author_check for name in [
            "линдгрен", "рид", "верн", "твен", "лондон", "дюма", "толкин", "толкиен",
            "конан дойл", "кристи", "по", "уэллс", "киплинг", "азимов", "лем",
            "диккенс", "скотт", "вайльд", "уайльд", "свифт", "дефо", "хаггард", "брэдбери"
        ])
        if is_foreign:
            ol_title = get_original_title_openlibrary(res.get("author", author), res.get("title", title))
            if ol_title:
                res["original_title"] = ol_title

    # Если запрошен пропуск габаритов/цены/аннотации (ручная сверка карточки)
    if skip_dimensions:
        for k in [
            "width", "length", "height", "weight",
            "width_mm", "length_mm", "height_mm", "weight_g", "dimensions",
            "price", "suggested_price", "old_price", "annotation"
        ]:
            res.pop(k, None)
    else:
        # Расчет физических параметров
        try:
            pages_val = res.get("pages") or 200
            cover_val = res.get("cover_type") or "Твердый переплет"
            paper_val = res.get("paper_type") or "Офсетная"
            fmt_val = res.get("book_format_code") or ""
            w_in = res.get("width_mm")
            l_in = res.get("length_mm")
            cw, cl, ch, cwt = calculate_dimensions_and_weight(
                pages=pages_val,
                cover_type=cover_val,
                paper_type=paper_val,
                format_code=fmt_val,
                width_mm=w_in,
                length_mm=l_in
            )
            res["width_mm"] = cw
            res["length_mm"] = cl
            res["height_mm"] = ch
            res["weight_g"] = cwt
        except Exception as e:
            print(f"[Enrichment] Ошибка расчета габаритов: {e}", flush=True)

    # Финальная гарантия по иллюстратору
    if not has_illustrations:
        res["illustrator"] = ""

    return res

