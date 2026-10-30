"""
config.py: Конфигурация и глобальные пути проекта Bookinistic Studio.
"""

import os
import shutil
from datetime import datetime
from typing import Optional

PORT = 8095
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOCS_DIR = os.path.join(BASE_DIR, "docs")
CREDENTIALS_DIR = os.path.join(BASE_DIR, "credentials")
ENV_FILE = os.path.join(BASE_DIR, ".env")

READY_TABLES_DIR = os.path.join(BASE_DIR, "ready_tables")
READY_TABLES_PRE2011_DIR = os.path.join(READY_TABLES_DIR, "1942-2010")
READY_TABLES_POST2011_DIR = os.path.join(READY_TABLES_DIR, "с_2011")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
INBOX_DIR = os.path.join(BASE_DIR, "storage/inbox")
VAULT_DIR = os.path.join(BASE_DIR, "storage/books_vault")
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
os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(CREDENTIALS_DIR, exist_ok=True)


def load_dotenv() -> None:
    """Загружает переменные окружения из файла .env, если он существует."""
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception as e:
            print(f"Ошибка чтения .env: {e}")


load_dotenv()


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
    """
    Возвращает настройки подключения к Yandex Object Storage (S3).
    Приоритет: 1) Переменные окружения (.env) -> 2) credentials/.yandex_s3_credentials -> 3) .yandex_s3_credentials в корне.
    """
    if os.environ.get("S3_BUCKET") and os.environ.get("S3_KEY_ID") and os.environ.get("S3_SECRET_KEY"):
        return {
            "bucket": os.environ.get("S3_BUCKET").strip(),
            "key_id": os.environ.get("S3_KEY_ID").strip(),
            "secret_key": os.environ.get("S3_SECRET_KEY").strip(),
            "endpoint_url": os.environ.get("S3_ENDPOINT_URL", "https://storage.yandexcloud.net").strip(),
            "region_name": os.environ.get("S3_REGION_NAME", "ru-central1").strip(),
        }
    candidates = [
        S3_CREDENTIALS_FILE,
        os.path.join(CREDENTIALS_DIR, ".yandex_s3_credentials"),
        os.path.join(CREDENTIALS_DIR, "yandex_s3.json"),
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            try:
                import json
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Ошибка чтения S3 credentials ({p}): {e}")
    return None


def get_saved_api_key() -> str:
    """
    Возвращает сохраненный API-ключ Gemini.
    Приоритет: 1) Переменная окружения GEMINI_API_KEY (.env) -> 2) credentials/.gemini_api_key -> 3) .gemini_api_key в корне.
    """
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ.get("GEMINI_API_KEY").strip()
    candidates = [
        KEY_FILE,
        os.path.join(CREDENTIALS_DIR, ".gemini_api_key"),
        os.path.join(CREDENTIALS_DIR, "gemini.key"),
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content and not content.startswith("#"):
                        return content
            except Exception:
                pass
    return ""


def save_api_key(key: str) -> None:
    """Сохраняет API-ключ в файл .gemini_api_key (и дублирует в credentials/)."""
    clean_key = key.strip()
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(clean_key)
    cred_file = os.path.join(CREDENTIALS_DIR, ".gemini_api_key")
    try:
        with open(cred_file, "w", encoding="utf-8") as f:
            f.write(clean_key)
    except Exception:
        pass


OZON_CREDENTIALS_FILE = os.path.join(BASE_DIR, ".ozon_credentials")


def get_ozon_config() -> Optional[dict]:
    """
    Возвращает настройки подключения к Ozon Seller API (client_id, api_key).
    Приоритет: 1) Переменные окружения (.env) -> 2) credentials/.ozon_credentials -> 3) .ozon_credentials в корне.
    """
    if os.environ.get("OZON_CLIENT_ID") and os.environ.get("OZON_API_KEY"):
        return {
            "client_id": os.environ.get("OZON_CLIENT_ID").strip(),
            "api_key": os.environ.get("OZON_API_KEY").strip(),
        }
    candidates = [
        OZON_CREDENTIALS_FILE,
        os.path.join(CREDENTIALS_DIR, ".ozon_credentials"),
        os.path.join(CREDENTIALS_DIR, "ozon.json"),
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            try:
                import json
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Ошибка чтения Ozon credentials ({p}): {e}")
    return None


def save_ozon_config(client_id: str, api_key: str) -> None:
    """Сохраняет Ozon credentials в файл .ozon_credentials (и дублирует в credentials/)."""
    import json
    data = {"client_id": str(client_id).strip(), "api_key": str(api_key).strip()}
    with open(OZON_CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    cred_file = os.path.join(CREDENTIALS_DIR, ".ozon_credentials")
    try:
        with open(cred_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass



