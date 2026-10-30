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
READY_TABLES_PRE2011_DIR = os.path.join(READY_TABLES_DIR, "1942-2010")
READY_TABLES_POST2011_DIR = os.path.join(READY_TABLES_DIR, "с_2011")
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
os.makedirs(READY_TABLES_PRE2011_DIR, exist_ok=True)
os.makedirs(READY_TABLES_POST2011_DIR, exist_ok=True)
os.makedirs(INBOX_DIR, exist_ok=True)
os.makedirs(VAULT_DIR, exist_ok=True)


def get_target_excel_file(mode: str) -> str:
    """
    Возвращает актуальный путь к готовой таблице за сегодняшнюю дату.
    Книги 1942-2010 сохраняются в папке ready_tables/1942-2010/.
    Книги с 2011 сохраняются в папке ready_tables/с_2011/.
    Если файла за сегодня ещё нет, инициализирует его из чистого шаблона Ozon.
    """
    today_str = datetime.now().strftime("%d.%m.%Y")
    if mode == "pre2011":
        folder = READY_TABLES_PRE2011_DIR
        os.makedirs(folder, exist_ok=True)
        filename = f"{today_str}_Печатная книга_до_2011.xlsx"
        target_path = os.path.join(folder, filename)

        # Проверяем миграцию: если файл остался в корне ready_tables/, переносим
        old_root_path = os.path.join(READY_TABLES_DIR, filename)
        if os.path.exists(old_root_path) and not os.path.exists(target_path):
            shutil.move(old_root_path, target_path)

        if not os.path.exists(target_path):
            if os.path.exists(BACKUP_FILE_PRE2011) and os.path.getsize(BACKUP_FILE_PRE2011) > 0:
                shutil.copyfile(BACKUP_FILE_PRE2011, target_path)
        return target_path
    else:
        folder = READY_TABLES_POST2011_DIR
        os.makedirs(folder, exist_ok=True)
        filename = f"{today_str}_Печатная книга_после_2011.xlsx"
        target_path = os.path.join(folder, filename)

        # Проверяем миграцию: если файл остался в корне ready_tables/, переносим
        old_root_path = os.path.join(READY_TABLES_DIR, filename)
        if os.path.exists(old_root_path) and not os.path.exists(target_path):
            shutil.move(old_root_path, target_path)

        if not os.path.exists(target_path):
            if os.path.exists(BACKUP_FILE_POST2011) and os.path.getsize(BACKUP_FILE_POST2011) > 0:
                shutil.copyfile(BACKUP_FILE_POST2011, target_path)
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


OZON_CREDENTIALS_FILE = os.path.join(BASE_DIR, ".ozon_credentials")


def get_ozon_config() -> Optional[dict]:
    """Возвращает настройки подключения к Ozon Seller API (client_id, api_key)."""
    if os.environ.get("OZON_CLIENT_ID") and os.environ.get("OZON_API_KEY"):
        return {
            "client_id": os.environ.get("OZON_CLIENT_ID").strip(),
            "api_key": os.environ.get("OZON_API_KEY").strip(),
        }
    if os.path.exists(OZON_CREDENTIALS_FILE):
        try:
            import json
            with open(OZON_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка чтения Ozon credentials: {e}")
    return None


def save_ozon_config(client_id: str, api_key: str) -> None:
    """Сохраняет Ozon credentials в файл .ozon_credentials."""
    import json
    data = {"client_id": str(client_id).strip(), "api_key": str(api_key).strip()}
    with open(OZON_CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)



