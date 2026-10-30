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

