"""
s3_service.py: Интеграция с Yandex Object Storage (S3) для выгрузки фото и генерации вечных ссылок Ozon.
"""

import base64
import json
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.config import Config

from config import get_card_image_path, get_s3_config
from core.domain.rules import get_canonical_photo_filename

# Надежный обход VPN-перехвата (utun4) для Yandex Cloud Object Storage
def _apply_direct_yandex_route():
    try:
        out = subprocess.check_output(['ifconfig', 'en0'], text=True)
        m = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', out)
        wifi_ip = m.group(1) if m else None
    except Exception:
        wifi_ip = None

    try:
        import urllib3.util.connection as urllib3_conn
        _orig_conn = urllib3_conn.create_connection
        def _patched_conn(address, *args, **kwargs):
            host, port = address
            if host in ('storage.yandexcloud.net', '213.180.193.243'):
                if wifi_ip:
                    kwargs['source_address'] = (wifi_ip, 0)
                return _orig_conn(('213.180.193.243', port), *args, **kwargs)
            return _orig_conn(address, *args, **kwargs)
        urllib3_conn.create_connection = _patched_conn
    except Exception:
        pass

_apply_direct_yandex_route()

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

    if slot == "info_pages":
        filename = f"archive/{get_canonical_photo_filename(slot, photo_index)}"
    else:
        filename = get_canonical_photo_filename(slot, photo_index, is_multi=photo_index > 1)

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
    slots_photos: Optional[Dict[str, Any]],
    force_upload: bool = False
) -> Tuple[Optional[str], str]:
    """
    Выгружает фото книги в Yandex S3 бакет under /{article}/...
    Если force_upload=False и фото уже было выгружено (имеет валидный s3_url), использует его.
    Если force_upload=True (например, при точечном обновлении фото товара), всегда выгружает
    свежие отредактированные байты и добавляет query-параметр версии ?v=... для сброса кэша CDN Ozon.
    Возвращает (main_photo_url, add_photo_urls_str).
    """
    client, bucket = get_s3_client()
    if not client or not bucket:
        return None, ""

    import time
    v_tag = f"?v={int(time.time())}"

    clean_title = re.sub(r"[^\w\s-]", "", title or "book").strip().replace(" ", "_")[:30]
    folder = f"{article}_{clean_title}".strip("_")

    main_photo_url: Optional[str] = None
    add_photo_urls: List[str] = []

    def _decode_photo(photo_obj) -> Optional[bytes]:
        if not photo_obj:
            return None
        from services.vault_service import resolve_photo_bytes
        return resolve_photo_bytes(photo_obj)

    def _archive_raw_source_s3(slot_tag: str, photo_obj: Any, idx: int = 1):
        if not isinstance(photo_obj, dict):
            return
        pid = photo_obj.get("id") or ""
        raw_bytes = None
        if pid and str(pid).startswith("ast_"):
            try:
                import services.asset_service as asset_service
                asset = asset_service.get_asset(pid)
                if asset and asset.original_path and os.path.exists(asset.original_path):
                    with open(asset.original_path, "rb") as f_orig:
                        raw_bytes = f_orig.read()
            except Exception:
                pass
        if not raw_bytes:
            raw_val = photo_obj.get("cameraOriginal") or photo_obj.get("rawOriginal")
            if raw_val:
                from services.vault_service import resolve_photo_bytes
                raw_bytes = resolve_photo_bytes(raw_val)

        if raw_bytes:
            upload_bytes(f"{folder}/raw_sources/{slot_tag}_{idx}_raw.jpg", raw_bytes)

    if slots_photos:
        # 1. Обложка (главное фото для Ozon)
        cf = slots_photos.get("cover_front")
        if cf:
            existing_s3 = cf.get("s3_url") if isinstance(cf, dict) else None
            if not force_upload and existing_s3 and "storage.yandexcloud.net" in existing_s3:
                main_photo_url = existing_s3
            else:
                data = _decode_photo(cf)
                if data:
                    fname = get_canonical_photo_filename("cover_front")
                    url = upload_bytes(f"{folder}/{fname}", data)
                    if url:
                        main_photo_url = f"{url}{v_tag}"
            _archive_raw_source_s3("cover_front", cf, 1)

        # 2. Фото дефектов при наличии (первые доп. фото)
        for idx, p in enumerate(slots_photos.get("mantra_defects", []), 1):
            existing_s3 = p.get("s3_url") if isinstance(p, dict) else None
            if not force_upload and existing_s3 and "storage.yandexcloud.net" in existing_s3:
                add_photo_urls.append(existing_s3)
            else:
                data = _decode_photo(p)
                if data:
                    fname = get_canonical_photo_filename("mantra_defects", idx)
                    url = upload_bytes(f"{folder}/{fname}", data)
                    if url:
                        add_photo_urls.append(f"{url}{v_tag}")
            _archive_raw_source_s3("defect", p, idx)

        # 3. Фото иллюстраций (если есть, идут перед задником)
        for idx, p in enumerate(slots_photos.get("illustrations", []), 1):
            existing_s3 = p.get("s3_url") if isinstance(p, dict) else None
            if not force_upload and existing_s3 and "storage.yandexcloud.net" in existing_s3:
                add_photo_urls.append(existing_s3)
            else:
                data = _decode_photo(p)
                if data:
                    fname = get_canonical_photo_filename("illustrations", idx)
                    url = upload_bytes(f"{folder}/{fname}", data)
                    if url:
                        add_photo_urls.append(f"{url}{v_tag}")
            _archive_raw_source_s3("illustration", p, idx)

        # 4. Фото задников книги (в конце перед карточкой; для комплектов — задник каждой книги)
        cb_raw = slots_photos.get("cover_back")
        cb_list = cb_raw if isinstance(cb_raw, list) else ([cb_raw] if cb_raw else [])
        for idx, p in enumerate(cb_list, 1):
            existing_s3 = p.get("s3_url") if isinstance(p, dict) else None
            if not force_upload and existing_s3 and "storage.yandexcloud.net" in existing_s3:
                add_photo_urls.append(existing_s3)
            else:
                data = _decode_photo(p)
                if data:
                    fname = get_canonical_photo_filename("cover_back", idx, is_multi=len(cb_list) > 1)
                    url = upload_bytes(f"{folder}/{fname}", data)
                    if url:
                        add_photo_urls.append(f"{url}{v_tag}")
            _archive_raw_source_s3("cover_back", p, idx)

        # Инфо-страницы (титул, оборот) — архивируем в облаке в подпапку archive/, НЕ передаем в Ozon ссылки!
        for idx, p in enumerate(slots_photos.get("info_pages", []), 1):
            existing_s3 = p.get("s3_url") if isinstance(p, dict) else None
            if force_upload or not (existing_s3 and "storage.yandexcloud.net" in existing_s3):
                data = _decode_photo(p)
                if data:
                    upload_bytes(f"{folder}/archive/info_page_{idx}.jpg", data)
            _archive_raw_source_s3("info_page", p, idx)

        # Сохраняем слепок book_state.json в S3 для точного восстановления
        try:
            state_data = {
                "article": article,
                "title": title,
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "slots_photos": slots_photos,
            }
            upload_bytes(
                f"{folder}/book_state.json",
                json.dumps(state_data, ensure_ascii=False, indent=2).encode("utf-8"),
                content_type="application/json"
            )
        except Exception as st_err:
            print(f"⚠️ Ошибка выгрузки book_state.json в S3: {st_err}")

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

