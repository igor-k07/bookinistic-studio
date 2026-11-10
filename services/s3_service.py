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


def upload_book_photos(
    article: str,
    title: str,
    slots_photos: Optional[Dict[str, Any]]
) -> Tuple[Optional[str], str]:
    """
    Выгружает фото книги в Yandex S3 бакет under /{article}/...
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
        if slots_photos.get("cover_front"):
            data = _decode_photo(slots_photos["cover_front"])
            if data:
                url = upload_bytes(f"{folder}/01_cover_front.jpg", data)
                if url:
                    main_photo_url = url

        # 2. Фото дефектов при наличии (первые доп. фото)
        for idx, p in enumerate(slots_photos.get("mantra_defects", []), 1):
            data = _decode_photo(p)
            if data:
                url = upload_bytes(f"{folder}/02_defect_{idx}.jpg", data)
                if url:
                    add_photo_urls.append(url)

        # 3. Фото иллюстраций
        for idx, p in enumerate(slots_photos.get("illustrations", []), 1):
            data = _decode_photo(p)
            if data:
                url = upload_bytes(f"{folder}/03_illustration_{idx}.jpg", data)
                if url:
                    add_photo_urls.append(url)

        # 4. Фото задней части книги
        if slots_photos.get("cover_back"):
            data = _decode_photo(slots_photos["cover_back"])
            if data:
                url = upload_bytes(f"{folder}/04_cover_back.jpg", data)
                if url:
                    add_photo_urls.append(url)

        # Инфо-страницы (титул, оборот) — архивируем в облаке в подпапку archive/, НЕ передаем в Ozon ссылки!
        for idx, p in enumerate(slots_photos.get("info_pages", []), 1):
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

