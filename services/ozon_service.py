"""
ozon_service.py: Интеграция с официальным Ozon Seller API.
Позволяет:
- Проверять авторизацию (Client-Id, Api-Key).
- Получать список существующих товаров продавца.
- Извлекать полные карточки товаров со всеми атрибутами и фото.
- Импортировать существующий каталог Ozon в локальную базу данных SQLite.
"""

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import get_ozon_config

OZON_API_BASE = "https://api-seller.ozon.ru"


def _make_ozon_request(endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
    """
    Выполняет POST-запрос к Ozon Seller API.
    Возвращает (success: bool, result_or_error: Any).
    """
    cfg = get_ozon_config()
    if not cfg or not cfg.get("client_id") or not cfg.get("api_key"):
        return False, "Не настроены Client-Id и Api-Key для Ozon Seller API"

    client_id = str(cfg["client_id"]).strip()
    api_key = str(cfg["api_key"]).strip()

    url = f"{OZON_API_BASE.rstrip('/')}/{endpoint.lstrip('/')}"
    data_bytes = json.dumps(payload or {}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={
            "Client-Id": client_id,
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "BookinisticStudio/1.0",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = resp.read().decode("utf-8")
            parsed = json.loads(resp_body)
            return True, parsed.get("result", parsed)
    except urllib.error.HTTPError as e:
        err_msg = f"HTTP {e.code}"
        try:
            err_json = json.loads(e.read().decode("utf-8"))
            err_msg = err_json.get("message") or err_json.get("error", err_msg)
            if "details" in err_json:
                err_msg += f" ({err_json['details']})"
        except Exception:
            pass
        return False, err_msg
    except Exception as e:
        return False, str(e)


def check_ozon_connection() -> Dict[str, Any]:
    """
    Проверяет валидность Client-Id и Api-Key через /v3/product/list (подходит для роли 'Товары' / Product).
    """
    ok, res = _make_ozon_request("/v3/product/list", {"filter": {"visibility": "ALL"}, "limit": 1})
    if ok and isinstance(res, dict):
        total_items = res.get("total") or res.get("total_items") or len(res.get("items", []))
        return {
            "success": True,
            "connected": True,
            "message": "Успешное подключение к Ozon Seller API (роль: Товары)",
            "total_products": total_items,
        }
    else:
        return {
            "success": False,
            "error": res,
        }


def get_all_ozon_product_ids(visibility: str = "ALL", limit_per_req: int = 1000) -> List[Dict[str, Any]]:
    """
    Итерируется по /v3/product/list и возвращает все товары продавца:
    [{ "product_id": 447624100, "offer_id": "DP-B-01557", "archived": False }, ...]
    """
    all_items: List[Dict[str, Any]] = []
    last_id = ""

    while True:
        payload = {
            "filter": {
                "visibility": visibility
            },
            "last_id": last_id,
            "limit": min(limit_per_req, 1000)
        }

        ok, res = _make_ozon_request("/v3/product/list", payload)
        if not ok or not isinstance(res, dict):
            print(f"⚠️ [Ozon API] Ошибка получения списка товаров: {res}")
            break

        items = res.get("items", [])
        if not items:
            break

        all_items.extend(items)
        last_id = res.get("last_id", "")
        total = res.get("total", 0)

        print(f"📦 [Ozon API] Получено {len(all_items)} из {total} товаров...")
        if not last_id or len(items) < limit_per_req:
            break

        time.sleep(0.1)  # вежливая пауза против rate-limit

    return all_items


def get_products_info_batch(product_ids: Optional[List[int]] = None, offer_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Запрашивает базовую информацию (цены, статусы, штрихкоды, фото) через /v3/product/info/list.
    Максимум 1000 товаров за один запрос.
    """
    payload: Dict[str, Any] = {}
    if product_ids:
        payload["product_id"] = product_ids[:1000]
    elif offer_ids:
        payload["offer_id"] = offer_ids[:1000]
    else:
        return []

    ok, res = _make_ozon_request("/v3/product/info/list", payload)
    if not ok or not isinstance(res, dict):
        print(f"⚠️ [Ozon API] Ошибка получения инфо товаров: {res}")
        return []

    return res.get("items", [])


def get_products_attributes_batch(product_ids: Optional[List[int]] = None, offer_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Запрашивает полные атрибуты товаров (автор, год, переплет, страницы, описание) через /v4/product/info/attributes.
    Максимум 50 товаров за один запрос.
    """
    payload: Dict[str, Any] = {
        "filter": {
            "visibility": "ALL"
        },
        "limit": 50
    }
    if product_ids:
        payload["filter"]["product_id"] = product_ids[:50]
        payload["limit"] = min(len(product_ids), 50)
    elif offer_ids:
        payload["filter"]["offer_id"] = offer_ids[:50]
        payload["limit"] = min(len(offer_ids), 50)
    else:
        return []

    ok, res = _make_ozon_request("/v4/product/info/attributes", payload)
    if not ok:
        print(f"⚠️ [Ozon API] Ошибка получения атрибутов товаров: {res}")
        return []

    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        return res.get("result", [])
    return []


def parse_ozon_book_to_catalog(item_info: Dict[str, Any], item_attrs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Преобразует данные товара Ozon (info + attributes) в унифицированную структуру книги Bookinistic:
    {
      "article": "DP-B-...",
      "title": "...",
      "author": "...",
      "year": 1985,
      "price": 450,
      "template_mode": "pre2011",
      "status": "imported",
      ...
    }
    """
    import re

    article = str(item_info.get("offer_id") or "").strip()
    title = str(item_info.get("name") or "").strip()
    price = 0.0
    try:
        price = float(str(item_info.get("price") or 0).replace(",", "."))
    except Exception:
        pass

    old_price = 0.0
    try:
        old_price = float(str(item_info.get("old_price") or 0).replace(",", "."))
    except Exception:
        pass

    barcodes = item_info.get("barcodes") or []
    barcode = str(item_info.get("barcode") or (barcodes[0] if barcodes else "")).strip()

    images = item_info.get("images") or []
    primary_image_raw = item_info.get("primary_image")
    if isinstance(primary_image_raw, list) and primary_image_raw:
        primary_image = primary_image_raw[0]
    elif isinstance(primary_image_raw, str):
        primary_image = primary_image_raw
    else:
        primary_image = images[0] if images else ""

    add_images = [img for img in images if img != primary_image]

    book: Dict[str, Any] = {
        "article": article,
        "title": title,
        "price": price,
        "old_price": old_price,
        "barcode": barcode,
        "main_photo_url": primary_image,
        "add_photo_urls": " ".join(add_images),
        "status": "imported",
        "ozon_product_id": item_info.get("id"),
    }

    # Точный маппинг атрибутов Ozon Seller API для категории "Печатная книга":
    # 105: Автор, 4182: Автор на обложке, 4180: Название, 4183: Оригинальное название,
    # 85: Издательство/Бренд, 1: Серия, 4081: Год выпуска, 4051: Страниц, 4184: ISBN,
    # 4191: Аннотация, 9356: Переплет, 8857: Сохранность, 23273: Направление/Жанр,
    # 8862: Возраст, 22391: Целевая аудитория, 112: Переводчик, 4082: Размеры
    if item_attrs:
        attributes = item_attrs.get("attributes", [])
        for attr in attributes:
            attr_id = attr.get("id")
            vals = [v.get("value", "") for v in attr.get("values", []) if isinstance(v, dict)]
            val_str = ", ".join(filter(None, vals)).strip()
            if not val_str:
                continue

            if attr_id == 105:
                book["author"] = val_str
            elif attr_id == 4182:
                book["author_cover"] = val_str
            elif attr_id == 4180 and val_str:
                book["title"] = val_str
            elif attr_id == 4183:
                book["original_title"] = val_str
            elif attr_id == 85:
                book["publisher"] = val_str
                book["brand"] = val_str
            elif attr_id == 1:
                book["series"] = val_str
            elif attr_id == 4081:
                m = re.findall(r"\d{4}", val_str)
                if m:
                    try:
                        book["year"] = int(m[0])
                    except Exception:
                        pass
            elif attr_id == 4051:
                m = re.findall(r"\d+", val_str)
                if m:
                    try:
                        book["pages"] = int(m[0])
                    except Exception:
                        pass
            elif attr_id == 4184:
                book["isbn"] = val_str
            elif attr_id == 4191:
                clean_ant = re.sub(r"<[^>]+>", "", val_str).strip()
                book["annotation"] = clean_ant
            elif attr_id == 9356:
                book["cover_type"] = val_str
            elif attr_id == 8857:
                book["condition"] = val_str
            elif attr_id == 23273:
                book["genre"] = val_str
            elif attr_id == 8862:
                book["age_limit"] = val_str
            elif attr_id == 22391:
                book["target_audience"] = val_str
            elif attr_id == 112:
                book["translator"] = val_str
            elif attr_id == 4082:
                book["dimensions"] = val_str

    if not book.get("author_cover") and book.get("author"):
        book["author_cover"] = book["author"]

    y = book.get("year")
    if y and isinstance(y, int) and y <= 2011:
        book["template_mode"] = "pre2011"
    else:
        book["template_mode"] = "post2011"

    return book


def import_all_ozon_cards_to_db(on_progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
    """
    Полный цикл импорта всех существующих карточек из Ozon в локальную базу SQLite:
    1. Запрашивает список всех товаров (offer_id / product_id).
    2. Пакетами получает детальную инфо и атрибуты.
    3. Преобразует и сохраняет в SQLite catalog.db (с авто-синхронизацией в S3).
    """
    from services.db_service import get_book_from_db, save_book_to_db

    print("🚀 [Ozon Import] Начат сбор списка товаров из Ozon...")
    items = get_all_ozon_product_ids()
    total_count = len(items)
    if total_count == 0:
        return {"success": True, "imported": 0, "total": 0, "message": "Товары в Ozon не найдены"}

    print(f"📦 [Ozon Import] Найдено {total_count} товаров в Ozon. Запуск загрузки характеристик...")

    imported = 0
    skipped = 0
    batch_size = 50

    for i in range(0, total_count, batch_size):
        chunk = items[i:i + batch_size]
        product_ids = [int(it["product_id"]) for it in chunk if it.get("product_id")]

        # 1. Получаем общую инфо (цены, ссылки на фото, штрихкод)
        info_items = get_products_info_batch(product_ids=product_ids)
        info_map = {int(it["id"]): it for it in info_items if "id" in it}

        # 2. Получаем детальные атрибуты (автор, год, страницы, аннотация)
        attr_items = get_products_attributes_batch(product_ids=product_ids)
        attr_map = {int(it["id"]): it for it in attr_items if "id" in it}

        for pid in product_ids:
            item_info = info_map.get(pid) or {"id": pid}
            item_attrs = attr_map.get(pid)

            book = parse_ozon_book_to_catalog(item_info, item_attrs)
            offer_id = book.get("article")
            if not offer_id:
                continue

            # Проверяем, есть ли уже такая книга в БД
            existing = get_book_from_db(offer_id)
            if existing:
                for k, v in book.items():
                    if v and (not existing.get(k) or k in ("ozon_product_id", "status", "price", "images")):
                        existing[k] = v
                save_book_to_db(existing, sync_s3=False)
                skipped += 1
            else:
                save_book_to_db(book, sync_s3=False)
                imported += 1

        if on_progress:
            on_progress(min(i + batch_size, total_count), total_count, imported, skipped)

        time.sleep(0.1)  # вежливая пауза

    # Финальная синхронизация базы в S3 после завершения всех пачек
    from services.db_service import backup_db_to_s3_async
    backup_db_to_s3_async()

    print(f"✅ [Ozon Import] Завершено! Импортировано новых: {imported}, обновлено существующих: {skipped} из {total_count}.")
    return {
        "success": True,
        "imported": imported,
        "updated": skipped,
        "total": total_count,
    }


_import_status: Dict[str, Any] = {
    "running": False,
    "progress": 0,
    "total": 0,
    "imported": 0,
    "updated": 0,
    "error": None,
    "done": False,
}


def get_import_status() -> Dict[str, Any]:
    """Возвращает текущий прогресс фонового импорта каталога."""
    return dict(_import_status)


def start_import_catalog_async() -> Dict[str, Any]:
    """Запускает процесс импорта каталога Ozon в отдельном потоке-демоне."""
    import threading
    global _import_status

    if _import_status.get("running"):
        return {"success": False, "error": "Импорт уже выполняется в фоновом режиме"}

    def _worker():
        global _import_status
        _import_status = {
            "running": True,
            "progress": 0,
            "total": 0,
            "imported": 0,
            "updated": 0,
            "error": None,
            "done": False,
        }
        try:
            def _on_progress(cur, tot, imp=0, upd=0):
                _import_status["progress"] = cur
                _import_status["total"] = tot
                _import_status["imported"] = imp
                _import_status["updated"] = upd

            res = import_all_ozon_cards_to_db(on_progress=_on_progress)
            _import_status["imported"] = res.get("imported", 0)
            _import_status["updated"] = res.get("updated", 0)
            _import_status["total"] = res.get("total", 0)
            _import_status["progress"] = res.get("total", 0)
            _import_status["done"] = True
        except Exception as e:
            _import_status["error"] = str(e)
        finally:
            _import_status["running"] = False

    t = threading.Thread(target=_worker, daemon=True, name="ozon_import_worker")
    t.start()
    return {"success": True, "message": "Импорт запущен в фоновом режиме"}


# Словарь сопоставления жанров книги со справочником Ozon API (атрибут 23273: «Направление»)
OZON_GENRE_MAP = {
    "проза": (972842193, "Проза"),
    "поэзия": (972842191, "Поэзия"),
    "стихи": (972842191, "Поэзия"),
    "фантастика": (972842200, "Фантастика"),
    "фэнтези": (972842203, "Фэнтези"),
    "детектив": (972841922, "Детектив"),
    "приключения": (972842192, "Приключения"),
    "история": (972842216, "История"),
    "биография": (972845201, "Биография"),
    "мемуары": (972845202, "Мемуары"),
    "биографии и мемуары": (972845201, "Биография"),
    "искусство и культура": (972842218, "Искусство и культура"),
    "искусство": (972842218, "Искусство и культура"),
    "научная и научно-популярная литература": (972842189, "Научная и научно-популярная литература"),
    "наука": (972842189, "Научная и научно-популярная литература"),
    "научно-популярное": (972842189, "Научная и научно-популярная литература"),
    "драматургия": (972841924, "Драматургия"),
    "публицистика": (972842196, "Публицистика"),
    "триллер": (972845207, "Триллер"),
    "мистика": (972845208, "Мистика"),
    "ужасы": (972842199, "Ужасы"),
    "эпос и фольклор": (972842202, "Эпос и фольклор"),
    "сказки": (972850201, "Дошкольное развитие детей"),
    "детская": (972850201, "Дошкольное развитие детей"),
    "детская литература": (972850201, "Дошкольное развитие детей"),
    "юриспруденция": (972842211, "Право и юриспруденция"),
    "медицина": (972842219, "Медицина"),
    "философия": (972842225, "Эзотерика и духовные практики"),
    "религия": (972842224, "Религия"),
    "словарь": (972863583, "Словарь"),
    "энциклопедия": (972842209, "Энциклопедия, справочник"),
    "кулинария": (972849921, "Кулинария"),
    "дом и сад": (972863367, "Дом и сад"),
    "спорт": (972845200, "Спорт"),
    "военное дело": (972863574, "Военное дело"),
}


def _build_ozon_book_attributes(book: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Формирует массив атрибутов категории «Печатная книга» по спецификации Ozon Seller API.
    """
    attributes: List[Dict[str, Any]] = []

    def _add_attr(attr_id: int, val: Any):
        if val is not None and str(val).strip():
            attributes.append({
                "id": attr_id,
                "values": [{"value": str(val).strip()}]
            })

    # 1. Обязательные системные атрибуты Ozon: Тип книги и код ТН ВЭД ЕАЭС
    attributes.append({
        "id": 8229,
        "values": [{"dictionary_value_id": 971445087, "value": "Печатная книга"}]
    })
    attributes.append({
        "id": 22232,
        "values": [{"dictionary_value_id": 971398243, "value": "4901990000 - Прочие книги, брошюры, листовки, аналогичные печатные издания, сброшюрованные"}]
    })

    # 2. Обязательный атрибут 23273: Направление (жанр книги из справочника Ozon)
    genre_raw = str(book.get("genre") or "").strip().lower()
    genre_entry = OZON_GENRE_MAP.get(genre_raw)
    if genre_entry:
        attributes.append({
            "id": 23273,
            "values": [{"dictionary_value_id": genre_entry[0], "value": genre_entry[1]}]
        })
    elif book.get("genre"):
        attributes.append({
            "id": 23273,
            "values": [{"value": str(book.get("genre")).strip()}]
        })
    else:
        attributes.append({
            "id": 23273,
            "values": [{"dictionary_value_id": 972842193, "value": "Проза"}]
        })

    # 3. Название и авторы
    title = str(book.get("title", "")).strip()
    _add_attr(4180, title)
    author = book.get("author") or book.get("author_cover") or "не указан"
    _add_attr(105, author)
    _add_attr(4182, book.get("author_cover") or author)
    if book.get("original_title"):
        _add_attr(4183, book.get("original_title"))

    # 4. Издательство, бренд, серия
    brand_val = book.get("brand") or book.get("publisher") or "Советский писатель"
    if brand_val and brand_val != "Нет бренда":
        _add_attr(85, brand_val)
    if book.get("publisher"):
        _add_attr(7, book.get("publisher"))
    if book.get("series"):
        _add_attr(1, book.get("series"))

    # 5. Характеристики издания
    if book.get("year"):
        _add_attr(4081, book.get("year"))
    if book.get("pages"):
        _add_attr(4051, book.get("pages"))
    if book.get("isbn"):
        _add_attr(4184, book.get("isbn"))
    if book.get("cover_type"):
        _add_attr(9356, book.get("cover_type"))
    if book.get("condition"):
        _add_attr(8857, book.get("condition"))
    if book.get("annotation") or book.get("description"):
        _add_attr(4191, book.get("annotation") or book.get("description"))
    if book.get("age_limit"):
        _add_attr(8862, book.get("age_limit"))
    if book.get("translator"):
        _add_attr(112, book.get("translator"))
    if book.get("dimensions"):
        _add_attr(4082, book.get("dimensions"))

    return attributes


def publish_product_to_ozon(book: Dict[str, Any]) -> Tuple[bool, Any]:
    """
    Публикует новый товар в Ozon Seller API через POST /v3/product/import.
    Поддерживает прямую загрузку книги со всеми фотографиями из S3/CDN.
    """
    article = str(book.get("article", "")).strip()
    if not article:
        return False, "Не указан артикул товара (offer_id)"

    title = str(book.get("title", "")).strip()
    if not title:
        return False, "Не указано название книги"

    price = str(book.get("price", "350")).strip()
    old_price = str(book.get("old_price", "")).strip() or str(round(float(price) * 1.4))

    # Определение категории Ozon в зависимости от года выпуска книги
    year_val = 0
    try:
        year_val = int(book.get("year") or 0)
    except (ValueError, TypeError):
        year_val = 0

    if 0 < year_val <= 1941:
        desc_cat_id = 200001486  # Антикварные издания (до 1941 г.)
    elif 1942 <= year_val <= 2010:
        desc_cat_id = 200001485  # Букинистические издания (1942-2010 гг.)
    else:
        desc_cat_id = 200001483  # Современные печатные издания (с 2011 г.)

    # Габариты упаковки (в мм) и вес (в граммах)
    width = int(book.get("width_package") or book.get("width") or 140)
    height = int(book.get("height_package") or book.get("height") or 22)
    depth = int(book.get("length_package") or book.get("length") or 215)
    weight = int(book.get("weight_package") or book.get("weight") or 330)

    # Фотографии товара
    main_photo = book.get("main_photo_url") or book.get("photo_main") or ""
    additional_photos_raw = book.get("add_photo_urls") or book.get("photos_additional") or ""
    if isinstance(additional_photos_raw, str):
        add_photos = [p.strip() for p in additional_photos_raw.split() if p.strip()]
    elif isinstance(additional_photos_raw, list):
        add_photos = [str(p).strip() for p in additional_photos_raw if str(p).strip()]
    else:
        add_photos = []

    all_images = []
    if main_photo:
        all_images.append(main_photo)
    for p in add_photos:
        if p and p != main_photo and p not in all_images:
            all_images.append(p)

    attributes = _build_ozon_book_attributes(book)

    item_payload = {
        "description_category_id": desc_cat_id,
        "type_id": 971445087,  # Тип товара Ozon: Печатная книга
        "name": title,
        "offer_id": article,
        "barcode": str(book.get("barcode", "")).strip(),
        "price": str(price),
        "old_price": str(old_price),
        "vat": "0",  # Не облагается НДС
        "dimension_unit": "mm",
        "weight_unit": "g",
        "width": width,
        "height": height,
        "depth": depth,
        "weight": weight,
        "primary_image": main_photo or (all_images[0] if all_images else ""),
        "images": all_images,
        "attributes": attributes,
    }

    payload = {"items": [item_payload]}
    return _make_ozon_request("/v3/product/import", payload)


def check_product_exists(offer_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Проверяет, существует ли товар на Ozon по offer_id (артикулу) через POST /v2/product/info.
    Возвращает (exists: bool, product_data: Optional[Dict]).
    """
    art = str(offer_id).strip()
    if not art:
        return False, None

    ok, res = _make_ozon_request("/v2/product/info", {"offer_id": art})
    if ok and isinstance(res, dict) and res.get("id"):
        return True, res
    return False, None


def update_ozon_product_attributes(book: Dict[str, Any]) -> Tuple[bool, Any]:
    """
    Обновляет текстовые характеристики существующего товара на Ozon через POST /v1/product/attributes/update.
    """
    article = str(book.get("article", "")).strip()
    if not article:
        return False, "Не указан артикул товара"

    attributes = _build_ozon_book_attributes(book)
    payload = {
        "items": [
            {
                "offer_id": article,
                "attributes": attributes
            }
        ]
    }
    return _make_ozon_request("/v1/product/attributes/update", payload)


def update_ozon_product_prices(offer_id: str, price: Any, old_price: Any = None) -> Tuple[bool, Any]:
    """
    Обновляет цены товара на Ozon через POST /v1/product/import/prices.
    """
    art = str(offer_id).strip()
    p_str = str(price).strip()
    op_str = str(old_price).strip() if old_price else str(round(float(p_str) * 1.4))

    payload = {
        "prices": [
            {
                "offer_id": art,
                "price": p_str,
                "old_price": op_str,
                "auto_action_enabled": "UNKNOWN",
            }
        ]
    }
    return _make_ozon_request("/v1/product/import/prices", payload)


def smart_publish_or_update(book: Dict[str, Any]) -> Dict[str, Any]:
    """
    Интеллектуальная публикация карточки книги на Ozon (Smart Update):
    1. Проверяет наличие ключей Ozon API.
    2. Автоматически определяет, существует ли товар с данным артикулом на Ozon.
    3. Если товар СУЩЕСТВУЕТ:
       - Обновляет атрибуты (/v1/product/attributes/update)
       - Обновляет фотографии (/v2/product/pictures/import)
       - Обновляет цены (/v1/product/import/prices)
    4. Если товар НОВЫЙ:
       - Создает товар целиком со всеми атрибутами и фото (/v3/product/import)
    Возвращает унифицированный словарь результата с task_id для отслеживания.
    """
    article = str(book.get("article", "")).strip()
    if not article:
        return {"success": False, "error": "Не указан артикул книги"}

    conn_status = check_ozon_connection()
    if not conn_status.get("connected"):
        return {
            "success": False,
            "skipped": True,
            "error": "Ozon Seller API не настроен (Client-Id / Api-Key отсутствуют в настройках)",
        }

    # 1. Проверяем существование товара на Ozon
    exists, existing_info = check_product_exists(article)

    # 2. ВЕТКА ОБНОВЛЕНИЯ (Товар уже есть на Ozon)
    if exists and existing_info:
        product_id = existing_info.get("id")
        attr_ok, attr_res = update_ozon_product_attributes(book)
        attr_task_id = (attr_res if isinstance(attr_res, dict) else {}).get("task_id")

        # Обновление фото, если ссылки переданы
        main_photo = book.get("main_photo_url") or book.get("photo_main") or ""
        add_photos = [u for u in (book.get("add_photo_urls") or "").split() if u]
        pic_task_id = None
        if main_photo:
            pic_ok, pic_res = update_ozon_product_pictures(article, main_photo, add_photos)
            if pic_ok and isinstance(pic_res, dict):
                pic_task_id = pic_res.get("task_id")

        # Обновление цен
        if book.get("price"):
            update_ozon_product_prices(article, book.get("price"), book.get("old_price"))

        primary_task_id = attr_task_id or pic_task_id
        return {
            "success": attr_ok,
            "action": "updated",
            "published": attr_ok,
            "task_id": primary_task_id,
            "product_id": product_id,
            "result": attr_res,
            "message": f"Карточка {article} успешно обновлена на Ozon (task_id: {primary_task_id})",
        }

    # 3. ВЕТКА СОЗДАНИЯ (Новый товар на Ozon)
    imp_ok, imp_res = publish_product_to_ozon(book)
    t_id = (imp_res if isinstance(imp_res, dict) else {}).get("task_id")
    if imp_ok:
        return {
            "success": True,
            "action": "imported",
            "published": True,
            "task_id": t_id,
            "result": imp_res,
            "message": f"Новая карточка {article} успешно отправлена на создание в Ozon (task_id: {t_id})",
        }
    else:
        return {
            "success": False,
            "action": "imported",
            "published": False,
            "error": str(imp_res),
            "result": imp_res,
        }


def get_import_task_info(task_id: int) -> Tuple[bool, Any]:
    """
    Проверка статуса обработки асинхронной задачи импорта/обновления товара (POST /v1/product/import/info).
    Возвращает статус модерации Ozon и подробные ошибки, если они есть.
    """
    return _make_ozon_request("/v1/product/import/info", {"task_id": int(task_id)})


def update_ozon_product_pictures(
    article: str,
    primary_image: str,
    images: Optional[List[str]] = None
) -> Tuple[bool, Any]:
    """
    Точечное обновление фотографий товара в Ozon Seller API (POST /v2/product/pictures/import).
    Обновляет галерею одного товара за 1-2 секунды без перезаливки таблицы.
    """
    all_imgs = []
    if primary_image:
        all_imgs.append(primary_image)
    if images:
        for im in images:
            if im and im not in all_imgs:
                all_imgs.append(im)

    if not all_imgs:
        return False, "Нет фотографий для отправки на Ozon"

    main_photo = primary_image or all_imgs[0]
    add_photos = [im for im in all_imgs if im != main_photo]

    payload = {
        "items": [
            {
                "offer_id": str(article).strip(),
                "primary_image": main_photo,
                "images": add_photos,
            }
        ]
    }
    return _make_ozon_request("/v2/product/pictures/import", payload)


def get_picture_import_status(task_id: int) -> Tuple[bool, Any]:
    """Проверка статуса асинхронного импорта картинок в Ozon (POST /v1/product/import/info)."""
    return _make_ozon_request("/v1/product/import/info", {"task_id": task_id})



