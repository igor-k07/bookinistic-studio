"""
config.py: Конфигурация и глобальные пути проекта Bookinistic Studio.
"""

import os
import shutil
from datetime import datetime
from typing import Optional

PORT = 8095
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

READY_TABLES_DIR = os.path.join(BASE_DIR, "ready_tables")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
INBOX_DIR = os.path.join(BASE_DIR, "storage/inbox")
VAULT_DIR = os.path.join(BASE_DIR, "storage/books_vault")
RAW_TEST_DIR = os.path.join(BASE_DIR, "books/test_raw")
KEY_FILE = os.path.join(BASE_DIR, ".gemini_api_key")
DRAFT_FILE = os.path.join(BASE_DIR, "storage/session_draft.json")
DB_PATH = os.path.join(BASE_DIR, "storage/catalog.db")

BACKUP_FILE_POST2011 = os.path.join(TEMPLATES_DIR, "Печатная книга_template.xlsx")
BACKUP_FILE_PRE2011 = os.path.join(TEMPLATES_DIR, "Печатная книга_до_2011_template.xlsx")
CARD_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "card.png")

# Гарантируем существование обязательных директорий
os.makedirs(READY_TABLES_DIR, exist_ok=True)
os.makedirs(INBOX_DIR, exist_ok=True)
os.makedirs(VAULT_DIR, exist_ok=True)


def get_target_excel_file(mode: str) -> str:
    """
    Возвращает актуальный путь к готовой таблице за сегодняшнюю дату в папке ready_tables.
    Если файла за сегодня ещё нет, инициализирует его из шаблона или существующей рабочей таблицы.
    """
    today_str = datetime.now().strftime("%d.%m.%Y")
    if mode == "pre2011":
        filename = f"{today_str}_Печатная книга_до_2011.xlsx"
        target_path = os.path.join(READY_TABLES_DIR, filename)
        if not os.path.exists(target_path):
            candidates = [
                os.path.join(READY_TABLES_DIR, f"Печатная книга_до_2011_{today_str}.xlsx"),
                os.path.join(READY_TABLES_DIR, "27.10.2026_Печатная книга_до_2011.xlsx"),
                os.path.join(READY_TABLES_DIR, "Печатная книга_до_2011_27.10.2026.xlsx"),
                os.path.join(BASE_DIR, "Печатная книга_26.10.2026.xlsx"),
                BACKUP_FILE_PRE2011,
            ]
            for c in candidates:
                if os.path.exists(c) and os.path.getsize(c) > 0:
                    shutil.copyfile(c, target_path)
                    break
        return target_path
    else:
        filename = f"{today_str}_Печатная книга_после_2011.xlsx"
        target_path = os.path.join(READY_TABLES_DIR, filename)
        if not os.path.exists(target_path):
            candidates = [
                os.path.join(READY_TABLES_DIR, f"Печатная книга_после_2011_{today_str}.xlsx"),
                os.path.join(READY_TABLES_DIR, "27.10.2026_Печатная книга_после_2011.xlsx"),
                os.path.join(READY_TABLES_DIR, "Печатная книга_после_2011_27.10.2026.xlsx"),
                os.path.join(BASE_DIR, "Печатная книга_ozon.xlsx"),
                BACKUP_FILE_POST2011,
            ]
            for c in candidates:
                if os.path.exists(c) and os.path.getsize(c) > 0:
                    shutil.copyfile(c, target_path)
                    break
        return target_path


def get_card_image_path() -> Optional[str]:
    """Возвращает актуальный путь к файлу постоянной инфо-карточки card.png"""
    candidates = [
        CARD_TEMPLATE_PATH,
        os.path.join(BASE_DIR, "storage/card.png"),
        os.path.join(BASE_DIR, "card.png"),
        os.path.join(INBOX_DIR, "card.PNG"),
        os.path.join(INBOX_DIR, "card.png"),
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None


S3_CREDENTIALS_FILE = os.path.join(BASE_DIR, ".yandex_s3_credentials")


def get_s3_config() -> Optional[dict]:
    """Возвращает настройки подключения к Yandex Object Storage (S3)."""
    if os.path.exists(S3_CREDENTIALS_FILE):
        try:
            import json
            with open(S3_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка чтения S3 credentials: {e}")
    return None


def get_saved_api_key() -> str:
    """Возвращает сохраненный API-ключ Gemini."""
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ.get("GEMINI_API_KEY").strip()
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def save_api_key(key: str) -> None:
    """Сохраняет API-ключ в файл .gemini_api_key."""
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key.strip())


