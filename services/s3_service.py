"""
s3_service.py: Интеграция с Yandex Object Storage (S3) для выгрузки фото и генерации вечных ссылок Ozon.
"""

import base64
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.config import Config

from config import get_card_image_path, get_s3_config

_s3_client = None
_s3_bucket = None


def get_s3_client():
    """Инициализирует и возвращает клиент boto3 S3."""
    global _s3_client, _s3_bucket
    if _s3_client is not None:
        return _s3_client, _s3_bucket

    cfg = get_s3_config()
    if not cfg:
        return None, None

    bucket = cfg.get("bucket", "another-piter-books1")
    key_id = cfg.get("key_id")
    secret_key = cfg.get("secret_key")
    endpoint = cfg.get("endpoint_url", "https://storage.yandexcloud.net")
    region = cfg.get("region_name", "ru-central1")

    if not key_id or not secret_key:
        return None, None

    try:
        session = boto3.session.Session()
        client = session.client(
            service_name="s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=5,
                read_timeout=15,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        _s3_client = client
        _s3_bucket = bucket
        return _s3_client, _s3_bucket
    except Exception as e:
        print(f"Ошибка создания клиента Yandex S3: {e}")
        return None, None


def upload_bytes(key: str, data: bytes, content_type: str = "image/jpeg") -> Optional[str]:
    """Загружает байты в бакет Yandex S3 и возвращает публичный URL."""
    client, bucket = get_s3_client()
    if not client or not bucket:
        return None

    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=86400",
        )
        return f"https://storage.yandexcloud.net/{bucket}/{key}"
    except Exception as e:
        print(f"Ошибка загрузки {key} в Yandex S3: {e}")
        return None


def upload_single_slot_photo(
    article: str,
    title: str,
    slot: str,
    photo_index: int,
    photo_obj: Any,
) -> Optional[str]:
    """
    Упреждающая выгрузка одного фото слота в Yandex S3 в фоновом режиме (Шаг 3 спецификации).
    Возвращает постоянный публичный HTTPS URL с параметром версионирования ?v=timestamp.
    """
    client, bucket = get_s3_client()
    if not client or not bucket:
        return None

    from services.vault_service import resolve_photo_bytes
    data = resolve_photo_bytes(photo_obj)
    if not data:
        return None

    clean_title = re.sub(r"[^\w\s-]", "", title or "book").strip().replace(" ", "_")[:30]
    folder = f"{article}_{clean_title}".strip("_")

    if slot == "cover_front":
        filename = "01_cover_front.jpg"
    elif slot == "mantra_defects":
        filename = f"02_defect_{photo_index}.jpg"
    elif slot == "illustrations":
        filename = f"03_illustration_{photo_index}.jpg"
    elif slot == "cover_back":
        suffix = f"_{photo_index}" if photo_index > 1 else ""
        filename = f"04_cover_back{suffix}.jpg"
    elif slot == "info_pages":
        filename = f"archive/info_page_{photo_index}.jpg"
    else:
        filename = f"photo_{photo_index}.jpg"

    key = f"{folder}/{filename}"
    url = upload_bytes(key, data)
    if url:
        import time
        versioned = f"{url}?v={int(time.time())}"
        print(f"☁️ [S3 Proactive] Фото {filename} выгружено в S3: {versioned}", flush=True)
        return versioned
    return None


def upload_book_photos(
    article: str,
    title: str,
    slots_photos: Optional[Dict[str, Any]]
) -> Tuple[Optional[str], str]:
    """
    Выгружает фото книги в Yandex S3 бакет under /{article}/...
    Если фото уже было выгружено упреждающе (имеет валидный s3_url), использует его без повторной заливки.
    Возвращает (main_photo_url, add_photo_urls_str):
    - main_photo_url: ссылка на 01_cover_front.jpg
    - add_photo_urls_str: разделенные пробелом ссылки на доп. фото (задник, иллюстрации, дефекты, card.png)
    * Замечание: служебные титулы (info_pages) сохраняются в {article}/archive/, но НЕ включаются в Ozon ссылки!
    """
    client, bucket = get_s3_client()
    if not client or not bucket:
        return None, ""

    clean_title = re.sub(r"[^\w\s-]", "", title or "book").strip().replace(" ", "_")[:30]
    folder = f"{article}_{clean_title}".strip("_")

    main_photo_url: Optional[str] = None
    add_photo_urls: List[str] = []

    def _decode_photo(photo_obj) -> Optional[bytes]:
        if not photo_obj:
            return None
        from services.vault_service import resolve_photo_bytes
        return resolve_photo_bytes(photo_obj)

    if slots_photos:
        # 1. Обложка (главное фото для Ozon)
        cf = slots_photos.get("cover_front")
        if cf:
            existing_s3 = cf.get("s3_url") if isinstance(cf, dict) else None
            if existing_s3 and "storage.yandexcloud.net" in existing_s3:
                main_photo_url = existing_s3
            else:
                data = _decode_photo(cf)
                if data:
                    url = upload_bytes(f"{folder}/01_cover_front.jpg", data)
                    if url:
                        main_photo_url = url

        # 2. Фото дефектов при наличии (первые доп. фото)
        for idx, p in enumerate(slots_photos.get("mantra_defects", []), 1):
            existing_s3 = p.get("s3_url") if isinstance(p, dict) else None
            if existing_s3 and "storage.yandexcloud.net" in existing_s3:
                add_photo_urls.append(existing_s3)
            else:
                data = _decode_photo(p)
                if data:
                    url = upload_bytes(f"{folder}/02_defect_{idx}.jpg", data)
                    if url:
                        add_photo_urls.append(url)

        # 3. Фото иллюстраций (если есть, идут перед задником)
        for idx, p in enumerate(slots_photos.get("illustrations", []), 1):
            existing_s3 = p.get("s3_url") if isinstance(p, dict) else None
            if existing_s3 and "storage.yandexcloud.net" in existing_s3:
                add_photo_urls.append(existing_s3)
            else:
                data = _decode_photo(p)
                if data:
                    url = upload_bytes(f"{folder}/03_illustration_{idx}.jpg", data)
                    if url:
                        add_photo_urls.append(url)

        # 4. Фото задников книги (в конце перед карточкой; для комплектов — задник каждой книги)
        cb_raw = slots_photos.get("cover_back")
        cb_list = cb_raw if isinstance(cb_raw, list) else ([cb_raw] if cb_raw else [])
        for idx, p in enumerate(cb_list, 1):
            existing_s3 = p.get("s3_url") if isinstance(p, dict) else None
            if existing_s3 and "storage.yandexcloud.net" in existing_s3:
                add_photo_urls.append(existing_s3)
            else:
                data = _decode_photo(p)
                if data:
                    suffix = f"_{idx}" if len(cb_list) > 1 else ""
                    url = upload_bytes(f"{folder}/04_cover_back{suffix}.jpg", data)
                    if url:
                        add_photo_urls.append(url)

        # Инфо-страницы (титул, оборот) — архивируем в облаке в подпапку archive/, НЕ передаем в Ozon ссылки!
        for idx, p in enumerate(slots_photos.get("info_pages", []), 1):
            existing_s3 = p.get("s3_url") if isinstance(p, dict) else None
            if not (existing_s3 and "storage.yandexcloud.net" in existing_s3):
                data = _decode_photo(p)
                if data:
                    upload_bytes(f"{folder}/archive/info_page_{idx}.jpg", data)

    # 5. Шаблонное фото с предупреждением (card.png) для каждой книги — всегда в самом конце
    card_path = get_card_image_path()
    card_url = None
    if card_path and os.path.exists(card_path):
        try:
            with open(card_path, "rb") as f:
                card_bytes = f.read()
            card_url = upload_bytes(f"{folder}/99_card.jpg", card_bytes)
        except Exception as e:
            print(f"Ошибка выгрузки card.png в S3: {e}")

    # Ограничение Ozon: максимум 14 дополнительных фото
    # Шаблонная карточка с предупреждением ВСЕГДА должна быть в самом конце
    if card_url:
        if len(add_photo_urls) >= 14:
            add_photo_urls = add_photo_urls[:13] + [card_url]
        else:
            add_photo_urls.append(card_url)
    else:
        add_photo_urls = add_photo_urls[:14]

    add_urls_str = " ".join(add_photo_urls) if add_photo_urls else ""

    print(f"✅ Успешно выгружено в Yandex S3: main={bool(main_photo_url)}, add={len(add_photo_urls)} фото")
    return main_photo_url, add_urls_str

