#!/usr/bin/env python3
"""
smart_ozon_s3_sync.py
=====================
CLI-утилита для запуска умной синхронизации карточек Ozon с облаком Yandex S3 и базой данных.
"""

import os
import sys
import argparse
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.sync_service import run_smart_ozon_s3_sync

def main():
    parser = argparse.ArgumentParser(description="Умная синхронизация карточек Ozon, Yandex S3 и catalog.db")
    parser.add_argument("--skip-ozon-check", action="store_true", help="Не опрашивать Ozon API на новые карточки")
    parser.add_argument("--workers", type=int, default=15, help="Количество параллельных потоков (по умолч. 15)")
    parser.add_argument("--limit", type=int, default=None, help="Лимит книг для тестового прогона")
    args = parser.parse_args()

    print("=" * 70)
    print(" 🚀 ЗАПУСК УМНОЙ СИНХРОНИЗАЦИИ: OZON -> YANDEX S3 -> CATALOG.DB")
    print("=" * 70)

    start_time = time.time()
    last_print = 0

    def _console_progress(status):
        nonlocal last_print
        now = time.time()
        stage = status.get("stage")
        msg = status.get("message")
        if stage == "syncing_photos":
            if now - last_print > 3 or status.get("progress") == status.get("total"):
                last_print = now
                prog = status.get("progress", 0)
                tot = status.get("total", 0)
                up = status.get("uploaded_photos", 0)
                pct = (prog / tot * 100) if tot > 0 else 100
                print(f"⏳ Прогресс: {prog}/{tot} ({pct:.1f}%) | Загружено фото в S3: {up}")
        elif stage in ("checking_ozon", "backup_db"):
            print(f"ℹ️ [{stage}] {msg}")

    res = run_smart_ozon_s3_sync(
        check_ozon_new=not args.skip_ozon_check,
        max_workers=args.workers,
        limit=args.limit,
        on_progress=_console_progress
    )

    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f" 🎉 УМНАЯ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА ЗА {elapsed / 60:.1f} МИН!")
    print(f" 📦 Новых карточек с Ozon: {res.get('new_ozon_cards', 0)}")
    print(f" ⏩ Пропущено книг (уже в S3): {res.get('skipped_books', 0)}")
    print(f" ☁️ Выгружено новых фото в S3: {res.get('uploaded_photos', 0)}")
    print(f" 💾 База данных скопирована в облако Yandex S3")
    print("=" * 70)

if __name__ == "__main__":
    main()
