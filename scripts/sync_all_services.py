#!/usr/bin/env python3
"""
Скрипт полной синхронизации сервисов: Ozon Seller API, Yandex Cloud S3 и SQLite catalog.db.

Шаги:
1. Создание локальной резервной копии storage/catalog.db.
2. Исправление опечаток в S3 (перенос папок на их правильные артикулы):
   - DP-B-02722_Кормчая_... -> DP-B-02732_Кормчая_книга_по_морю_житейско/
   - DP-B-02825_Ася_...     -> DP-B-02826_Ася_Первая_любовь_Вешние_воды/
3. Очистка мусорных и дублирующих папок в S3 (_book, голые артикулы, тесты, фантомы).
4. Импорт/обновление всех 2077 карточек из Ozon в catalog.db.
5. Привязка постоянных ссылок Yandex S3 ко всем обработанным книгам в catalog.db.
6. Отправка обновленных ссылок S3 на Ozon для товаров со временными/битыми ссылками.
7. Резервное копирование актуальной БД в S3 (backups/db/catalog_latest.db).
"""

import os
import sys

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import shutil
import time
import json
import re
import sqlite3
from typing import Dict, List, Any, Optional

from services.s3_service import get_s3_client, _s3_bucket
from services.ozon_service import (
    get_all_ozon_product_ids,
    get_products_info_batch,
    get_products_attributes_batch,
    parse_ozon_book_to_catalog,
    update_ozon_product_pictures,
    _make_ozon_request
)

DB_PATH = "storage/catalog.db"
BACKUP_LOCAL_PATH = "storage/catalog.db.bak_pre_sync"

# Мусорные и дублирующие папки для удаления из S3
JUNK_FOLDERS = [
    'test/',
    'DP-B-02882_Тестовая_Книга_Архитектуры/',
    'DP-B-02882_Тестовая_книга_E2E_Архитектура/',
    'DP-B-02883_Тестовая_Книга_Архитектуры/',
    'DP-B-02883_Тестовая_книга_E2E_Архитектура/',
    'DP-B-03082/', 'DP-B-03082_book/',
    'DP-B-03083/',
    'DP-B-03084/', 'DP-B-03084_book/', 'DP-B-03084_Хиромантия_Как_понять_свою_суд/',
    'DP-B-03085/',
    'DP-B-03086/',
    'DP-B-03087/', 'DP-B-03087_book/', 'DP-B-03087_Возвращение_в_Брайдсхед/',
    'DP-B-03088/',
    'DP-B-03089/',
    'DP-B-03090/',
    'DP-B-03091_book/', 'DP-B-03091_Моя_жизнь_с_Чаплином_Интимные/',
    'DP-B-03096_book/', 'DP-B-03096_Как_выйти_замуж_Как_победить_с/',
    'DP-B-03102_book/', 'DP-B-03102_Прорыв_начать_на_рассвете/',
    'DP-B-03109_book/', 'DP-B-03109_Поджигатели_Но_пасаран/',
    'DP-B-03117_book/', 'DP-B-03117_Как_получить_то_о_чем_вы_всегд/',
    'DP-B-03126_book/', 'DP-B-03126_Что_такое_психология_Том_2/',
]

# Папки для переноса (старый префикс -> новый префикс)
RENAME_FOLDERS = [
    ('DP-B-02722_Кормчая_книга_по_морю_житейско/', 'DP-B-02732_Кормчая_книга_по_морю_житейско/'),
    ('DP-B-02825_Ася_Первая_любовь_Вешние_воды/', 'DP-B-02826_Ася_Первая_любовь_Вешние_воды/'),
]


def step1_backup_db():
    print("📁 [Шаг 1] Резервное копирование storage/catalog.db...")
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, BACKUP_LOCAL_PATH)
        print(f"✅ Локальный бэкап сохранен: {BACKUP_LOCAL_PATH}")
    else:
        print("⚠️ База данных не найдена по пути:", DB_PATH)


def step2_rename_typo_folders(s3, bucket):
    print("\n📦 [Шаг 2] Исправление опечаток в артикулах папок S3...")
    for old_prefix, new_prefix in RENAME_FOLDERS:
        res = s3.list_objects_v2(Bucket=bucket, Prefix=old_prefix)
        contents = res.get('Contents', [])
        if not contents:
            print(f"  Пропуск {old_prefix} (не найдено объектов)")
            continue
        print(f"  Перенос {old_prefix} -> {new_prefix} ({len(contents)} файлов)...")
        for obj in contents:
            old_key = obj['Key']
            rel_path = old_key[len(old_prefix):]
            new_key = f"{new_prefix}{rel_path}"
            # Копируем объект
            s3.copy_object(
                Bucket=bucket,
                CopySource={'Bucket': bucket, 'Key': old_key},
                Key=new_key
            )
            # Удаляем старый
            s3.delete_object(Bucket=bucket, Key=old_key)
        print(f"  ✅ Перенесено: {new_prefix}")


def step3_cleanup_junk_folders(s3, bucket):
    print("\n🧹 [Шаг 3] Удаление мусорных/дублирующих папок в S3...")
    deleted_count = 0
    for prefix in JUNK_FOLDERS:
        res = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        contents = res.get('Contents', [])
        if not contents:
            continue
        print(f"  Удаление {prefix} ({len(contents)} файлов)...")
        delete_keys = [{'Key': o['Key']} for o in contents]
        s3.delete_objects(Bucket=bucket, Delete={'Objects': delete_keys})
        deleted_count += len(delete_keys)
    print(f"✅ Всего удалено {deleted_count} мусорных файлов из S3.")


def step4_sync_ozon_to_db():
    print("\n🔄 [Шаг 4] Синхронизация всех карточек Ozon в catalog.db...")
    from services.db_service import get_book_from_db, save_book_to_db

    items = get_all_ozon_product_ids()
    total_count = len(items)
    print(f"📦 Найдено {total_count} товаров в Ozon. Загрузка данных пачками по 50...")

    batch_size = 50
    imported = 0
    updated = 0

    for i in range(0, total_count, batch_size):
        chunk = items[i:i + batch_size]
        product_ids = [int(it["product_id"]) for it in chunk if it.get("product_id")]

        info_items = get_products_info_batch(product_ids=product_ids)
        info_map = {int(it["id"]): it for it in info_items if "id" in it}

        attr_items = get_products_attributes_batch(product_ids=product_ids)
        attr_map = {int(it["id"]): it for it in attr_items if "id" in it}

        for pid in product_ids:
            item_info = info_map.get(pid) or {"id": pid}
            item_attrs = attr_map.get(pid)

            book = parse_ozon_book_to_catalog(item_info, item_attrs)
            offer_id = book.get("article")
            if not offer_id:
                continue

            existing = get_book_from_db(offer_id)
            if existing:
                # Обновляем поля, НЕ затирая ссылки на S3, если они уже есть
                for k, v in book.items():
                    if k in ("main_photo_url", "add_photo_urls"):
                        cur_val = existing.get(k) or ""
                        # Если в БД уже лежит ссылка на Yandex S3, не перетираем ее ссылкой Ozon CDN
                        if "yandexcloud" in cur_val:
                            continue
                    if v and (not existing.get(k) or k in ("ozon_product_id", "price", "title")):
                        existing[k] = v
                save_book_to_db(existing, sync_s3=False)
                updated += 1
            else:
                save_book_to_db(book, sync_s3=False)
                imported += 1

        print(f"  Обработано {min(i + batch_size, total_count)} / {total_count}...")
        time.sleep(0.05)

    print(f"✅ Синхронизация Ozon завершена: новых добавлено {imported}, обновлено {updated}.")


def step5_link_s3_to_db(s3, bucket):
    print("\n🔗 [Шаг 5] Привязка S3-фотографий к карточкам в catalog.db...")
    from services.db_service import get_book_from_db, save_book_to_db

    paginator = s3.get_paginator('list_objects_v2')
    s3_folders = set()
    for page in paginator.paginate(Bucket=bucket, Delimiter='/'):
        for p in page.get('CommonPrefixes', []):
            s3_folders.add(p['Prefix'])

    linked_count = 0
    for folder in sorted(s3_folders):
        m = re.match(r'^(DP-[A-Z]-\d+|Кн-\d+-\d+)', folder)
        if not m:
            continue
        art = m.group(1)

        # Собираем витринные фото из папки (исключая archive/ и raw_sources/)
        res = s3.list_objects_v2(Bucket=bucket, Prefix=folder)
        all_objs = res.get('Contents', [])
        
        showcase_files = []
        for o in all_objs:
            key = o['Key']
            rel = key[len(folder):]
            if rel.startswith('archive/') or rel.startswith('raw_sources/'):
                continue
            if rel.endswith('.json') or rel.endswith('/'):
                continue
            showcase_files.append(rel)

        if not showcase_files:
            continue

        # Сортируем: 01_cover_front сначала, затем дефекты, иллюстрации, 04_cover_back, 99_card
        showcase_files.sort()

        main_photo_key = showcase_files[0]
        # Если есть 01_cover_front, он точно главный
        for f in showcase_files:
            if '01_cover_front' in f:
                main_photo_key = f
                break

        add_photo_keys = [f for f in showcase_files if f != main_photo_key]

        main_url = f"https://storage.yandexcloud.net/{bucket}/{folder}{main_photo_key}"
        add_urls = " ".join([f"https://storage.yandexcloud.net/{bucket}/{folder}{f}" for f in add_photo_keys])

        db_book = get_book_from_db(art)
        if not db_book:
            db_book = {"article": art}

        db_book["main_photo_url"] = main_url
        db_book["add_photo_urls"] = add_urls
        db_book["status"] = "ready"
        save_book_to_db(db_book, sync_s3=False)
        linked_count += 1
        print(f"  ✅ {art} -> привязано {1 + len(add_photo_keys)} фото из {folder}")

    print(f"✅ Всего к S3 привязано {linked_count} книг в catalog.db.")


def step6_fix_temporary_ozon_links():
    print("\n🌐 [Шаг 6] Проверка временных ссылок на витрине Ozon...")
    from services.db_service import get_book_from_db

    # Товары, у которых на Ozon были временные tunnel ссылки
    check_arts = ['DP-B-03087', 'DP-B-03088']
    for art in check_arts:
        db_book = get_book_from_db(art)
        if not db_book or not db_book.get("main_photo_url"):
            continue
        main_url = db_book["main_photo_url"]
        adds = (db_book.get("add_photo_urls") or "").split()
        print(f"  Отправка актуальных фото S3 для {art} на Ozon...")
        ok, res = update_ozon_product_pictures(art, main_url, adds)
        if ok:
            print(f"  ✅ Ozon принял фото для {art} (task_id: {res.get('task_id')})")
        else:
            print(f"  ⚠️ Ошибка Ozon для {art}: {res}")


def step7_backup_to_s3():
    print("\n☁️ [Шаг 7] Сохранение актуального бэкапа БД в S3...")
    from services.db_service import backup_db_to_s3
    res = backup_db_to_s3()
    if res.get("ok"):
        print(f"✅ Бэкап БД успешно загружен в S3: {res.get('latest_key')}")
    else:
        print(f"⚠️ Ошибка бэкапа в S3: {res.get('error')}")


def main():
    print("=" * 60)
    print("🚀 Запуск полной синхронизации Ozon + Yandex S3 + catalog.db")
    print("=" * 60)

    s3, bucket = get_s3_client()
    if not s3 or not bucket:
        print("❌ Ошибка: не удалось подключиться к Yandex Cloud S3.")
        sys.exit(1)

    step1_backup_db()
    step2_rename_typo_folders(s3, bucket)
    step3_cleanup_junk_folders(s3, bucket)
    step4_sync_ozon_to_db()
    step5_link_s3_to_db(s3, bucket)
    step6_fix_temporary_ozon_links()
    step7_backup_to_s3()

    print("\n" + "=" * 60)
    print("🎉 ВСЕ СЕРВИСЫ УСПЕШНО СИНХРОНИЗИРОВАНЫ!")
    print("=" * 60)


if __name__ == "__main__":
    main()
