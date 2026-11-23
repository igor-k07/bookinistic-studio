"""
system_controller.py: Контроллер системных утилит, документации, Ozon API и Cloudflare.
"""

import os
import re
import subprocess
from typing import Any, Dict
import urllib.parse

from config import (
    BASE_DIR,
    DOCS_DIR,
    PORT,
    READY_TABLES_DIR,
    READY_TABLES_POST2011_DIR,
    READY_TABLES_PRE2011_DIR,
    get_ozon_config,
    get_saved_api_key,
    get_target_excel_file,
    save_api_key,
    save_ozon_config,
)
from server.router import RequestContext
from services.db_service import (
    backup_db_to_s3,
    get_catalog_references,
    get_db_sync_status,
    get_next_article_number,
    restore_db_from_s3,
)
import services.ozon_service as ozon_service
import services.tunnel_service as tunnel_service
from services.vault_service import create_photos_zip
from core.use_cases.cleanup_temp_files import CleanupTempFilesUseCase


def get_tunnel_url(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/get_tunnel_url"""
    url = tunnel_service.get_tunnel_url()
    local_url = tunnel_service.get_local_url(PORT)
    local_ip = tunnel_service.get_local_ip()
    return {
        "url": url or "",
        "local_url": local_url,
        "local_ip": local_ip,
        "has_vpn": tunnel_service.is_vpn_active(),
    }


def restart_tunnel(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/restart_tunnel"""
    new_url = tunnel_service.restart_tunnel(PORT)
    return {
        "success": True,
        "url": new_url or "",
        "local_url": tunnel_service.get_local_url(PORT),
        "local_ip": tunnel_service.get_local_ip(),
        "has_vpn": tunnel_service.is_vpn_active(),
    }


def get_references(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/references"""
    return {"success": True, "references": get_catalog_references()}


def get_sync_status(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/db_sync_status"""
    return {"success": True, "sync": get_db_sync_status()}


def backup_db(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/backup_db"""
    return backup_db_to_s3()


def restore_db(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/restore_db"""
    return restore_db_from_s3()


def save_key(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/save_key"""
    body = ctx.get_json()
    save_api_key(body.get("key", ""))
    return {"success": True}


def get_key(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/get_key"""
    return {"key": get_saved_api_key()}


def get_memos(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/get_memos"""
    memo_defs = [
        {
            "id": "SPECIFICATION.md",
            "title": "Техническая спецификация проекта",
            "category": "Архитектура & Регламент",
            "icon": "📑",
            "badge": "SRS 1.0",
            "badge_color": "bg-indigo-500/20 text-indigo-300 border-indigo-500/40",
            "desc": "Главный регламент системы: фото-конвейер, правила rembg, разделение зон ответственности, S3 и Ozon.",
        },
        {
            "id": "OZON_FIELDS_GUIDE.md",
            "title": "Поля Ozon и правила заполнения",
            "category": "Ozon & Каталог",
            "icon": "📋",
            "badge": "Главная",
            "badge_color": "bg-amber-500/20 text-amber-300 border-amber-500/40",
            "desc": "Справочник всех 81/86 колонок Ozon, обязательная ручная цена, 12 типов бумаги, авторы, ГОСТ-габариты и вес.",
        },
        {
            "id": "OZON_DICTIONARIES.md",
            "title": "Официальные словари Ozon",
            "category": "Ozon & Каталог",
            "icon": "📖",
            "badge": "Словари",
            "badge_color": "bg-blue-500/20 text-blue-300 border-blue-500/40",
            "desc": "16 типов обложек, 12 типов бумаги, 56 жанров Ozon, 5 градаций сохранности и возрастные маркировки.",
        },
        {
            "id": "OZON_BRANDS.md",
            "title": "Справочник 397 брендов Ozon",
            "category": "Ozon & Каталог",
            "icon": "🏷️",
            "badge": "397 брендов",
            "badge_color": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
            "desc": "Реестр подтвержденных брендов Ozon из catalog.db, рейтинг ТОП-30 и правила подстановки «Нет бренда».",
        },
        {
            "id": "KEYS_GUIDE.md",
            "title": "Справочник по ключам и API",
            "category": "Безопасность & Доступы",
            "icon": "🔑",
            "badge": "Ключи",
            "badge_color": "bg-purple-500/20 text-purple-300 border-purple-500/40",
            "desc": "Карта ключей: Gemini AI, Ozon Seller API, Yandex S3, Cloudflare Tunnel, .env и приоритеты загрузки.",
        },
        {
            "id": "PHOTO_PIPELINE.md",
            "title": "Регламент фотосъемки и ракурсов",
            "category": "Склад & Съемка",
            "icon": "📸",
            "badge": "Фото",
            "badge_color": "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
            "desc": "Ракурсы съемки (обложка, титул, мантра, дефекты), постоянная карточка card.png, обрезка и S3 CDN.",
        },
        {
            "id": "BARCODE_CHEAT_SHEET.md",
            "title": "Штрихкоды и термоэтикетки",
            "category": "Склад & Съемка",
            "icon": "🏷️",
            "badge": "EAN-13",
            "badge_color": "bg-rose-500/20 text-rose-300 border-rose-500/40",
            "desc": "Генерация штрихкодов EAN-13 из артикула, работа с ISBN и печать этикеток 58х40 мм для Ozon.",
        },
        {
            "id": "TECH_STACK.md",
            "title": "Архитектура и технический стек",
            "category": "Разработка",
            "icon": "💻",
            "badge": "Стек",
            "badge_color": "bg-slate-500/20 text-slate-300 border-slate-500/40",
            "desc": "Техническое описание, прямой парсер OpenXML Excel, схема SQLite catalog.db и REST API.",
        },
    ]
    result = []
    for m in memo_defs:
        fpath = os.path.join(DOCS_DIR, m["id"])
        exists = os.path.exists(fpath)
        size_kb = round(os.path.getsize(fpath) / 1024, 1) if exists else 0
        item = dict(m)
        item["exists"] = exists
        item["size_kb"] = size_kb
        result.append(item)
    return {"success": True, "memos": result, "docs_dir": DOCS_DIR}


def open_guide(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/open_guide"""
    doc_name = ctx.get_query("name", "OZON_FIELDS_GUIDE.md")
    clean_name = os.path.basename(doc_name)
    candidates = [
        os.path.join(DOCS_DIR, clean_name),
        os.path.join(BASE_DIR, clean_name),
    ]
    target_doc = None
    for p in candidates:
        if os.path.exists(p):
            target_doc = p
            break
    if not target_doc:
        target_doc = os.path.join(DOCS_DIR, "OZON_FIELDS_GUIDE.md")

    subprocess.Popen(["open", target_doc])
    return {
        "success": True,
        "file": target_doc,
        "filename": os.path.basename(target_doc),
        "rel_path": os.path.relpath(target_doc, BASE_DIR),
    }


def open_ready_folder(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/open_ready_folder"""
    mode = ctx.get_query("mode")
    if mode == "pre2011":
        folder_to_open = READY_TABLES_PRE2011_DIR
    elif mode in ("post2011", "post"):
        folder_to_open = READY_TABLES_POST2011_DIR
    else:
        folder_to_open = READY_TABLES_DIR

    subprocess.Popen(["open", folder_to_open])
    return {
        "success": True,
        "path": folder_to_open,
        "rel_path": os.path.relpath(folder_to_open, BASE_DIR),
    }


def open_docs_folder(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/open_docs_folder"""
    subprocess.Popen(["open", DOCS_DIR])
    return {
        "success": True,
        "path": DOCS_DIR,
        "rel_path": os.path.relpath(DOCS_DIR, BASE_DIR),
    }


def reveal_file(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/reveal_file"""
    mode = ctx.get_query("mode", "pre2011")
    target_file = get_target_excel_file(mode)
    folder = os.path.dirname(target_file)
    subprocess.Popen(["open", "-R", target_file])
    return {
        "success": True,
        "file": target_file,
        "filename": os.path.basename(target_file),
        "folder": folder,
        "rel_folder": os.path.relpath(folder, BASE_DIR),
    }


def ozon_status(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/ozon/status"""
    cfg = get_ozon_config()
    if not cfg or not cfg.get("client_id") or not cfg.get("api_key"):
        return {
            "configured": False,
            "message": "Ключи Ozon Seller API не настроены",
            "next_article": get_next_article_number(),
        }
    status_res = ozon_service.check_ozon_connection()
    cid = str(cfg.get("client_id", ""))
    masked_cid = (cid[:4] + "***") if len(cid) > 4 else "***"
    return {
        "configured": True,
        "client_id": masked_cid,
        "next_article": get_next_article_number(),
        **status_res,
    }


def ozon_save_keys(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/ozon/save_keys"""
    body = ctx.get_json()
    client_id = body.get("client_id", "").strip()
    api_key = body.get("api_key", "").strip()
    if not client_id or not api_key:
        raise ValueError("Необходимо указать Client-Id и Api-Key")
    save_ozon_config(client_id, api_key)
    conn_test = ozon_service.check_ozon_connection()
    return {"success": True, "connection": conn_test}


def ozon_start_import(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/ozon/start_import"""
    return ozon_service.start_import_catalog_async()


def ozon_import_status(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/ozon/import_status"""
    st = ozon_service.get_import_status()
    return {"success": True, "status": st}


def ozon_task_status(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/ozon/task_status?task_id=...: Статус задачи обработки карточки на Ozon."""
    task_id_raw = ctx.get_query("task_id", "").strip()
    if not task_id_raw:
        return {"success": False, "error": "Не передан task_id"}
    try:
        t_id = int(task_id_raw)
    except ValueError:
        return {"success": False, "error": "Некорректный task_id (ожидается число)"}

    ok, res = ozon_service.get_import_task_info(t_id)
    if ok:
        return {"success": True, "result": res}
    return {"success": False, "error": str(res)}


def smart_s3_sync_start(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/sync/smart_s3: Запуск умной синхронизации Ozon -> S3 -> DB"""
    from services.sync_service import start_smart_s3_sync_async
    return start_smart_s3_sync_async()


def smart_s3_sync_status(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/sync/smart_s3/status: Статус умной синхронизации"""
    from services.sync_service import get_smart_s3_sync_status
    return {"success": True, "status": get_smart_s3_sync_status()}


def download_excel(ctx: RequestContext) -> None:
    """GET /api/download_excel"""
    h = ctx.handler
    mode = ctx.get_query("mode", "pre2011")
    target_file = get_target_excel_file(mode)
    filename = os.path.basename(target_file)
    if os.path.exists(target_file):
        ascii_name = f"Pechatnaya_kniga_{mode}.xlsx"
        encoded_name = urllib.parse.quote(filename)
        h.send_response(200)
        h.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        h.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}')
        h.end_headers()
        with open(target_file, "rb") as f:
            h.wfile.write(f.read())
    else:
        h.send_response(404)
        h.end_headers()


def download_photos_zip(ctx: RequestContext) -> None:
    """GET /api/download_photos_zip"""
    h = ctx.handler
    article_req = (ctx.get_query("article", "")).strip()
    zip_bytes, zip_filename = create_photos_zip(article_req)
    ascii_name = re.sub(r"[^\w.-]", "_", zip_filename)
    encoded_name = urllib.parse.quote(zip_filename)

    h.send_response(200)
    h.send_header("Content-Type", "application/zip")
    h.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}')
    h.send_header("Content-Length", str(len(zip_bytes)))
    h.end_headers()
    h.wfile.write(zip_bytes)


def cleanup_temp(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/cleanup_temp: сборщик мусора устаревших временных фотографий."""
    body = {}
    try:
        if ctx.handler.headers.get("Content-Length"):
            body = ctx.get_json()
    except Exception:
        body = {}
    max_age = float(body.get("max_age_hours", 24.0)) if body else 24.0
    dry_run = bool(body.get("dry_run", False)) if body else False
    use_case = CleanupTempFilesUseCase()
    return use_case.execute(max_age_hours=max_age, dry_run=dry_run)


