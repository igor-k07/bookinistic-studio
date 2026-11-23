"""
config.py: Конфигурация и глобальные пути проекта Bookinistic Studio.
"""

import os
import shutil
import socket
from datetime import datetime
from typing import Optional

# Надежный обход DNS-перехвата VPN/Fake-IP (198.18.x.x) для Yandex Cloud Object Storage
_orig_getaddrinfo = socket.getaddrinfo

def _patched_getaddrinfo(host, port, *args, **kwargs):
    if host == "storage.yandexcloud.net":
        # Официальный публичный IP Яндекс Хранилища, доступный напрямую без VPN-задержек
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("213.180.193.243", port))]
    return _orig_getaddrinfo(host, port, *args, **kwargs)

socket.getaddrinfo = _patched_getaddrinfo

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
SESSION_PHOTOS_DIR = os.path.join(BASE_DIR, "storage/session_photos")
SESSION_ASSETS_DIR = os.path.join(BASE_DIR, "storage/session_assets")
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
os.makedirs(SESSION_PHOTOS_DIR, exist_ok=True)
os.makedirs(SESSION_ASSETS_DIR, exist_ok=True)
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


def save_ozon_config(client_id: str, api_key: str, profile_name: Optional[str] = None) -> None:
    """Сохраняет Ozon credentials в файл .ozon_credentials (и дублирует в credentials/)."""
    import json
    data = {
        "client_id": str(client_id).strip(),
        "api_key": str(api_key).strip(),
        "active_profile": profile_name or ("test" if str(client_id).strip() == "2727930" else "primary"),
    }
    with open(OZON_CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    cred_file = os.path.join(CREDENTIALS_DIR, ".ozon_credentials")
    try:
        with open(cred_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_active_store_id() -> str:
    """Возвращает идентификатор (client_id) текущего активного магазина Ozon."""
    cfg = get_ozon_config()
    if cfg and cfg.get("client_id"):
        return str(cfg.get("client_id")).strip()
    return "870997"


def get_store_dir(store_id: Optional[str] = None) -> str:
    """Возвращает изолированную директорию хранилища для указанного магазина."""
    s_id = str(store_id or get_active_store_id()).strip()
    d = os.path.join(BASE_DIR, "storage", "stores", s_id)
    os.makedirs(d, exist_ok=True)
    return d


def get_db_path(store_id: Optional[str] = None) -> str:
    """
    Возвращает путь к базе данных catalog.db для указанного (или активного) магазина.
    Для основного магазина (870997) сохраняет совместимость с storage/catalog.db.
    Для тестового магазина (2727930) использует storage/stores/2727930/catalog.db.
    """
    s_id = str(store_id or get_active_store_id()).strip()
    store_dir = get_store_dir(s_id)
    store_db = os.path.join(store_dir, "catalog.db")

    if s_id in ("870997", "primary"):
        legacy_db = os.path.join(BASE_DIR, "storage", "catalog.db")
        if not os.path.exists(store_db) and os.path.exists(legacy_db):
            try:
                os.link(legacy_db, store_db)
            except Exception:
                shutil.copy2(legacy_db, store_db)
        return store_db if os.path.exists(store_db) else legacy_db

    return store_db


def get_vault_dir(store_id: Optional[str] = None) -> str:
    """Возвращает путь к архиву книг books_vault для магазина."""
    s_id = str(store_id or get_active_store_id()).strip()
    if s_id in ("870997", "primary"):
        return os.path.join(BASE_DIR, "storage", "books_vault")
    store_dir = get_store_dir(s_id)
    v_dir = os.path.join(store_dir, "books_vault")
    os.makedirs(v_dir, exist_ok=True)
    return v_dir


def get_draft_file_path(store_id: Optional[str] = None) -> str:
    """Возвращает путь к файлу черновика сессии для магазина."""
    s_id = str(store_id or get_active_store_id()).strip()
    if s_id in ("870997", "primary"):
        return os.path.join(BASE_DIR, "storage", "session_draft.json")
    return os.path.join(get_store_dir(s_id), "session_draft.json")


def get_ready_tables_dir(store_id: Optional[str] = None) -> str:
    """Возвращает корневую папку готовых таблиц Excel для магазина."""
    s_id = str(store_id or get_active_store_id()).strip()
    if s_id in ("870997", "primary"):
        return READY_TABLES_DIR
    p = os.path.join(READY_TABLES_DIR, "stores", s_id)
    os.makedirs(p, exist_ok=True)
    return p


def get_target_excel_file(mode: str, store_id: Optional[str] = None) -> str:
    """
    Возвращает актуальный путь к готовой таблице за сегодняшнюю дату.
    Книги 1942-2010 сохраняются в папке 1942-2010/.
    Книги с 2011 сохраняются в папке с_2011/.
    Если файла за сегодня ещё нет, инициализирует его из чистого шаблона Ozon.
    """
    base_folder = get_ready_tables_dir(store_id)
    today_str = datetime.now().strftime("%d.%m.%Y")
    if mode == "pre2011":
        folder = os.path.join(base_folder, "1942-2010") if base_folder != READY_TABLES_DIR else READY_TABLES_PRE2011_DIR
        os.makedirs(folder, exist_ok=True)
        filename = f"{today_str}_Печатная книга_до_2011.xlsx"
        target_path = os.path.join(folder, filename)

        if base_folder == READY_TABLES_DIR:
            old_root_path = os.path.join(READY_TABLES_DIR, filename)
            if os.path.exists(old_root_path) and not os.path.exists(target_path):
                shutil.move(old_root_path, target_path)

        if not os.path.exists(target_path):
            if os.path.exists(BACKUP_FILE_PRE2011) and os.path.getsize(BACKUP_FILE_PRE2011) > 0:
                shutil.copyfile(BACKUP_FILE_PRE2011, target_path)
        return target_path
    else:
        folder = os.path.join(base_folder, "с_2011") if base_folder != READY_TABLES_DIR else READY_TABLES_POST2011_DIR
        os.makedirs(folder, exist_ok=True)
        filename = f"{today_str}_Печатная книга_после_2011.xlsx"
        target_path = os.path.join(folder, filename)

        if base_folder == READY_TABLES_DIR:
            old_root_path = os.path.join(READY_TABLES_DIR, filename)
            if os.path.exists(old_root_path) and not os.path.exists(target_path):
                shutil.move(old_root_path, target_path)

        if not os.path.exists(target_path):
            if os.path.exists(BACKUP_FILE_POST2011) and os.path.getsize(BACKUP_FILE_POST2011) > 0:
                shutil.copyfile(BACKUP_FILE_POST2011, target_path)
        return target_path


def get_ozon_profiles() -> dict:
    """Возвращает список сохраненных профилей магазинов Ozon и текущий активный профиль."""
    import json
    cur = get_ozon_config() or {}
    cur_id = str(cur.get("client_id", "")).strip()

    profiles = []
    for prof_key, prof_filename, default_name in [
        ("primary", "ozon_primary.json", "Основной магазин"),
        ("test", "ozon_test.json", "Тестовый магазин"),
    ]:
        p_path = os.path.join(CREDENTIALS_DIR, prof_filename)
        if os.path.exists(p_path):
            try:
                with open(p_path, "r", encoding="utf-8") as f:
                    p_data = json.load(f)
                    profiles.append({
                        "key": prof_key,
                        "name": p_data.get("name", default_name),
                        "client_id": str(p_data.get("client_id", "")),
                        "is_active": (str(p_data.get("client_id", "")) == cur_id),
                    })
            except Exception:
                pass

    active_key = "test" if cur_id == "2727930" else "primary"
    return {
        "active_key": active_key,
        "active_client_id": cur_id,
        "profiles": profiles,
    }


def switch_ozon_profile(profile_key: str) -> bool:
    """Переключает активный магазин Ozon (primary или test)."""
    import json
    prof_filename = f"ozon_{profile_key}.json"
    p_path = os.path.join(CREDENTIALS_DIR, prof_filename)
    if not os.path.exists(p_path):
        return False

    with open(p_path, "r", encoding="utf-8") as f:
        p_data = json.load(f)
        client_id = p_data.get("client_id")
        api_key = p_data.get("api_key")
        if client_id and api_key:
            save_ozon_config(client_id, api_key, profile_name=profile_key)
            update_active_store_paths()
            return True
    return False


def update_active_store_paths():
    global DB_PATH, VAULT_DIR, DRAFT_FILE
    DB_PATH = get_db_path()
    VAULT_DIR = get_vault_dir()
    DRAFT_FILE = get_draft_file_path()


# Инициализируем пути под текущий активный магазин
update_active_store_paths()



