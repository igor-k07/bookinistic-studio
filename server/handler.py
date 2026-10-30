"""
handler.py: HTTP обработчик запросов BatchHandler для Bookinistic Studio.
"""

import base64
import http.server
import json
import os
import re
import socket
import subprocess
import time
import urllib.parse
from typing import Any, Dict

from config import (
    BASE_DIR,
    DOCS_DIR,
    DRAFT_FILE,
    INBOX_DIR,
    PORT,
    READY_TABLES_DIR,
    READY_TABLES_PRE2011_DIR,
    READY_TABLES_POST2011_DIR,
    TEMPLATES_DIR,
    VAULT_DIR,
    get_card_image_path,
    get_saved_api_key,
    get_target_excel_file,
    save_api_key,
    get_ozon_config,
    save_ozon_config,
)
from server.state import check_mobile_events, record_mobile_upload
from services.ai_service import call_gemini_vision
from services.excel_service import (
    append_book_to_excel,
    clear_excel_table,
    delete_book_from_excel,
    get_current_books,
)
from services.db_service import (
    init_db,
    save_book_to_db,
    get_book_from_db,
    delete_book_from_db,
    get_all_books_from_db,
    get_next_article_number,
    backup_db_to_s3,
    restore_db_from_s3,
    get_db_sync_status,
    get_catalog_references,
    reconcile_with_references,
)
import services.ozon_service as ozon_service
import services.tunnel_service as tunnel_service
from services.vault_service import create_photos_zip, save_book_vault_photos
from services.s3_service import upload_book_photos as s3_upload_book_photos
from services.image_service import process_image_ai
from services.enrichment_service import enrich_book_metadata


class BatchHandler(http.server.BaseHTTPRequestHandler):
    """Основной HTTP обработчик веб-интерфейса и REST API."""

    def setup(self):
        super().setup()
        try:
            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

    def log_message(self, format, *args):
        # Отключаем дефолтный спам логов базового сервера
        pass

    def end_headers(self):
        super().end_headers()
        if self.command == "HEAD":
            self._orig_wfile = self.wfile
            class DevNull:
                closed = False
                def write(self, *args, **kwargs): pass
                def flush(self): pass
                def close(self): self.closed = True
            self.wfile = DevNull()

    def finish(self):
        if hasattr(self, "_orig_wfile"):
            self.wfile = self._orig_wfile
        try:
            super().finish()
        except Exception:
            pass

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # -------------------------------------------------------------
    # Вспомогательные методы отправки ответов
    # -------------------------------------------------------------
    def send_json(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def send_error_json(self, error: Any, status: int = 500):
        self.send_json({"success": False, "error": str(error)}, status=status)

    def serve_template(self, filename: str):
        """Отдает HTML-шаблон из папки templates/."""
        tpl_path = os.path.join(TEMPLATES_DIR, filename)
        if os.path.exists(tpl_path):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(tpl_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    # -------------------------------------------------------------
    # GET ЗАПРОСЫ
    # -------------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            self.serve_template("desktop.html")

        elif parsed.path == "/mobile":
            self.serve_template("mobile.html")

        elif parsed.path == "/api/get_tunnel_url":
            url = tunnel_service.get_tunnel_url()
            local_url = tunnel_service.get_local_url(PORT)
            local_ip = tunnel_service.get_local_ip()
            self.send_json({
                "url": url or "",
                "local_url": local_url,
                "local_ip": local_ip,
                "has_vpn": tunnel_service.tunnel_manager.is_vpn_active()
            })

        elif parsed.path == "/api/restart_tunnel":
            new_url = tunnel_service.restart_tunnel(PORT)
            self.send_json({
                "success": True,
                "url": new_url or "",
                "local_url": tunnel_service.get_local_url(PORT),
                "local_ip": tunnel_service.get_local_ip(),
                "has_vpn": tunnel_service.tunnel_manager.is_vpn_active()
            })

        elif parsed.path == "/api/check_mobile_event":
            query = urllib.parse.parse_qs(parsed.query)
            last_client_id = int(query.get("last_id", ["0"])[0])
            self.send_json(check_mobile_events(last_client_id))

        elif parsed.path == "/api/references":
            try:
                refs = get_catalog_references()
                self.send_json({"success": True, "references": refs})
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/load_test_batch":
            self.send_json({"success": True, "photos": []})

        elif parsed.path == "/api/get_books":
            qs = urllib.parse.parse_qs(parsed.query)
            mode = qs.get("mode", ["pre2011"])[0]
            pre_books = get_current_books("pre2011")
            post_books = get_current_books("post2011")
            current_list = pre_books if mode == "pre2011" else post_books
            self.send_json({
                "success": True,
                "mode": mode,
                "books": current_list,
                "pre2011_count": len(pre_books),
                "post2011_count": len(post_books),
                "total": len(pre_books) + len(post_books)
            })

        elif parsed.path == "/api/get_next_article":
            try:
                next_art = get_next_article_number()
                self.send_json({"success": True, "article": next_art})
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/get_db_catalog":
            try:
                qs = urllib.parse.parse_qs(parsed.query)
                mode = qs.get("mode", [None])[0]
                status = qs.get("status", [None])[0]
                search = qs.get("search", [None])[0]
                db_books = get_all_books_from_db(mode=mode, status=status, search=search)
                self.send_json({
                    "success": True,
                    "count": len(db_books),
                    "books": db_books
                })
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/db_sync_status":
            try:
                status_info = get_db_sync_status()
                self.send_json({"success": True, "sync": status_info})
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/ozon/status":
            try:
                cfg = get_ozon_config()
                if not cfg or not cfg.get("client_id") or not cfg.get("api_key"):
                    self.send_json({"configured": False, "message": "Ключи Ozon Seller API не настроены", "next_article": get_next_article_number()})
                else:
                    status_res = ozon_service.check_ozon_connection()
                    cid = str(cfg.get("client_id", ""))
                    masked_cid = (cid[:4] + "***") if len(cid) > 4 else "***"
                    self.send_json({
                        "configured": True,
                        "client_id": masked_cid,
                        "next_article": get_next_article_number(),
                        **status_res
                    })
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/ozon/import_status":
            try:
                st = ozon_service.get_import_status()
                self.send_json({"success": True, "status": st})
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/download_excel":
            qs = urllib.parse.parse_qs(parsed.query)
            mode = qs.get("mode", ["pre2011"])[0]
            target_file = get_target_excel_file(mode)
            filename = os.path.basename(target_file)
            if os.path.exists(target_file):
                ascii_name = f"Pechatnaya_kniga_{mode}.xlsx"
                encoded_name = urllib.parse.quote(filename)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}")
                self.end_headers()
                with open(target_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()

        elif parsed.path == "/api/open_ready_folder":
            qs = urllib.parse.parse_qs(parsed.query)
            mode = qs.get("mode", [None])[0]
            if mode == "pre2011":
                folder_to_open = READY_TABLES_PRE2011_DIR
            elif mode in ("post2011", "post"):
                folder_to_open = READY_TABLES_POST2011_DIR
            else:
                folder_to_open = READY_TABLES_DIR
            try:
                subprocess.Popen(["open", folder_to_open])
                self.send_json({
                    "success": True,
                    "path": folder_to_open,
                    "rel_path": os.path.relpath(folder_to_open, BASE_DIR)
                })
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/open_guide":
            qs = urllib.parse.parse_qs(parsed.query)
            doc_name = qs.get("name", ["OZON_FIELDS_GUIDE.md"])[0]
            # Защита от выхода за пределы директории
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

            try:
                subprocess.Popen(["open", target_doc])
                self.send_json({
                    "success": True,
                    "file": target_doc,
                    "filename": os.path.basename(target_doc),
                    "rel_path": os.path.relpath(target_doc, BASE_DIR)
                })
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/open_docs_folder":
            try:
                subprocess.Popen(["open", DOCS_DIR])
                self.send_json({
                    "success": True,
                    "path": DOCS_DIR,
                    "rel_path": os.path.relpath(DOCS_DIR, BASE_DIR)
                })
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/get_memos":
            memo_defs = [
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
            self.send_json({"success": True, "memos": result, "docs_dir": DOCS_DIR})

        elif parsed.path == "/api/reveal_file":
            qs = urllib.parse.parse_qs(parsed.query)
            mode = qs.get("mode", ["pre2011"])[0]
            target_file = get_target_excel_file(mode)
            folder = os.path.dirname(target_file)
            try:
                subprocess.Popen(["open", "-R", target_file])
                self.send_json({
                    "success": True,
                    "file": target_file,
                    "filename": os.path.basename(target_file),
                    "folder": folder,
                    "rel_folder": os.path.relpath(folder, BASE_DIR)
                })
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/get_key":
            self.send_json({"key": get_saved_api_key()})

        elif parsed.path == "/api/get_session_draft":
            if os.path.exists(DRAFT_FILE) and os.path.getsize(DRAFT_FILE) > 5:
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    with open(DRAFT_FILE, "rb") as f:
                        self.wfile.write(f.read())
                    return
                except Exception:
                    pass
            self.send_json({"has_draft": False})

        elif parsed.path in ("/card.png", "/templates/card.png", "/storage/card.png"):
            card_path = get_card_image_path()
            if card_path and os.path.exists(card_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                with open(card_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()

        elif parsed.path in ("/qrcode.min.js", "/static/qrcode.min.js"):
            qr_file = os.path.join(TEMPLATES_DIR, "qrcode.min.js")
            if os.path.exists(qr_file):
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(qr_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()

        elif parsed.path in ("/cropper.min.js", "/static/cropper.min.js"):
            cropper_js = os.path.join(TEMPLATES_DIR, "cropper.min.js")
            if os.path.exists(cropper_js):
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(cropper_js, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()

        elif parsed.path in ("/cropper.min.css", "/static/cropper.min.css"):
            cropper_css = os.path.join(TEMPLATES_DIR, "cropper.min.css")
            if os.path.exists(cropper_css):
                self.send_response(200)
                self.send_header("Content-Type", "text/css; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(cropper_css, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()

        elif parsed.path.startswith("/vault/"):
            rel_path = urllib.parse.unquote(parsed.path[len("/vault/"):])
            safe_rel_path = os.path.normpath(rel_path).lstrip("/\\")
            if safe_rel_path.startswith(".."):
                self.send_response(403)
                self.end_headers()
                return

            full_file_path = os.path.join(VAULT_DIR, safe_rel_path)

            # Если путь не найден напрямую, ищем по артикулу: /vault/{article}/{filename}
            if not (os.path.exists(full_file_path) and os.path.isfile(full_file_path)) and "/" in safe_rel_path:
                parts = safe_rel_path.split("/", 1)
                art_prefix = parts[0]
                inner_file = parts[1]
                if os.path.exists(VAULT_DIR):
                    for d in os.listdir(VAULT_DIR):
                        if d == art_prefix or d.startswith(f"{art_prefix}_"):
                            cand = os.path.join(VAULT_DIR, d, inner_file)
                            if os.path.exists(cand) and os.path.isfile(cand):
                                full_file_path = cand
                                break

            if os.path.exists(full_file_path) and os.path.isfile(full_file_path):
                # Определяем реальный mime-тип по сигнатуре файла
                try:
                    with open(full_file_path, "rb") as f_chk:
                        magic = f_chk.read(16)
                    if magic.startswith(b"\xff\xd8\xff"):
                        content_type = "image/jpeg"
                    elif magic.startswith(b"\x89PNG\r\n\x1a\n"):
                        content_type = "image/png"
                    elif magic.startswith(b"RIFF") and b"WEBP" in magic:
                        content_type = "image/webp"
                    else:
                        ext = os.path.splitext(full_file_path)[1].lower()
                        content_type = "image/jpeg" if ext in (".jpg", ".jpeg") else ("image/png" if ext == ".png" else "application/octet-stream")
                except Exception:
                    content_type = "image/jpeg"

                file_size = os.path.getsize(full_file_path)
                t0_req = time.time()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                if self.command != "HEAD":
                    with open(full_file_path, "rb") as f:
                        while True:
                            chunk = f.read(262144)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                t_spent = time.time() - t0_req
                ua = self.headers.get("User-Agent", "Unknown")[:40]
                print(f"📸 [VAULT] 200 OK ({file_size // 1024} KB in {t_spent:.2f}s) -> {safe_rel_path} [{ua}]", flush=True)
            else:
                self.send_response(404)
                self.end_headers()

        elif parsed.path == "/api/download_photos_zip":
            qs = urllib.parse.parse_qs(parsed.query)
            article_req = qs.get("article", [""])[0].strip()
            zip_bytes, zip_filename = create_photos_zip(article_req)

            ascii_name = re.sub(r"[^\w.-]", "_", zip_filename)
            encoded_name = urllib.parse.quote(zip_filename)

            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}')
            self.send_header("Content-Length", str(len(zip_bytes)))
            self.end_headers()
            self.wfile.write(zip_bytes)

        else:
            self.send_response(404)
            self.end_headers()

    # -------------------------------------------------------------
    # POST ЗАПРОСЫ
    # -------------------------------------------------------------
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        if parsed.path == "/api/mobile_upload":
            try:
                body = json.loads(post_data.decode("utf-8"))
                images = body.get("images", [])
                if not images:
                    raise Exception("Нет изображений в запросе")

                session_ts = int(time.time())
                for idx, img in enumerate(images):
                    fname = f"mobile_batch_{session_ts}_{idx+1}.jpg"
                    p = os.path.join(INBOX_DIR, fname)
                    with open(p, "wb") as f:
                        f.write(base64.b64decode(img.get("data", "")))

                record_mobile_upload(session_ts, images)
                self.send_json({"success": True, "count": len(images)})
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/ai_recognize_book":
            try:
                body = json.loads(post_data.decode("utf-8"))
                api_key = (body.get("api_key") or "").strip() or get_saved_api_key()
                if not api_key:
                    raise Exception("API ключ Gemini не введен! Нажмите «Ввести API ключ» в правом верхнем углу интерфейса.")
                images = body.get("images", [])
                if not images:
                    raise Exception("Нет изображений для распознавания! Добавьте фото в слот или выберите фото в ленте.")

                print(f"[/api/ai_recognize_book] Запрос распознавания: {len(images)} фото...", flush=True)
                result = call_gemini_vision(images, api_key)

                # Проверяем наличие слота иллюстраций в запросе
                has_illustrations = any("иллюстрац" in (img.get("role_name") or "").lower() for img in images) or bool(body.get("has_illustrations"))

                # Вторичная сверка и обогащение в сложных случаях (FantLab / Open Library)
                try:
                    result = enrich_book_metadata(result, has_illustrations=has_illustrations)
                except Exception as enrich_e:
                    print(f"[/api/ai_recognize_book] Обогащение пропущено: {enrich_e}", flush=True)

                self.send_json({"success": True, "data": result})
            except Exception as e:
                import traceback
                print(f"[/api/ai_recognize_book] ОШИБКА: {e}", flush=True)
                traceback.print_exc()
                self.send_json({"success": False, "error": str(e)})

        elif parsed.path == "/api/enrich_book":
            try:
                body = json.loads(post_data.decode("utf-8")) if post_data else {}
                book_in = body.get("book", {})
                has_illustrations = bool(body.get("has_illustrations", True))
                enriched = enrich_book_metadata(book_in, has_illustrations=has_illustrations)
                self.send_json({"success": True, "data": enriched})
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/save_book":
            try:
                book_data = json.loads(post_data.decode("utf-8"))
                # Нечувствительная к регистру сверка и канонизация по базе catalog.db
                try:
                    book_data = reconcile_with_references(book_data)
                except Exception as rec_err:
                    print(f"⚠️ Ошибка канонизации при сохранении: {rec_err}")

                mode = book_data.get("template_mode")
                if not mode:
                    year_val = str(book_data.get("year", "")).strip()
                    try:
                        y_int = int(year_val)
                        mode = "pre2011" if y_int <= 2011 else "post2011"
                    except Exception:
                        mode = "pre2011"

                article = str(book_data.get("article") or "").strip()
                if not article:
                    article = get_next_article_number()
                    book_data["article"] = article

                title = book_data.get("title", "")

                # 1. Сохраняем обработанные фото книги в архив storage/books_vault/
                slots_photos = book_data.get("slots_photos")
                folder_name, saved_files = save_book_vault_photos(
                    article,
                    title,
                    slots_photos
                )

                # 2. Выгружаем фото в Yandex S3 (приоритетный источник постоянных ссылок Ozon)
                s3_main_url, s3_add_urls = None, ""
                try:
                    s3_main_url, s3_add_urls = s3_upload_book_photos(article, title, slots_photos)
                except Exception as s3_err:
                    print(f"⚠️ Ошибка S3 выгрузки (переключаемся на туннель): {s3_err}")

                tunnel_url = ""
                if s3_main_url:
                    book_data["main_photo_url"] = s3_main_url
                    book_data["add_photo_urls"] = s3_add_urls
                else:
                    # Fallback: Cloudflare Quick Tunnel для публичных ссылок Ozon
                    tunnel_url = tunnel_service.get_tunnel_url()
                    if not tunnel_url:
                        tunnel_url = tunnel_service.start_tunnel(PORT)

                    if tunnel_url and article and saved_files:
                        main_photo = "01_cover_front.jpg" if "01_cover_front.jpg" in saved_files else saved_files[0]
                        book_data["main_photo_url"] = f"{tunnel_url}/vault/{article}/{main_photo}"

                        add_files = [f for f in saved_files if f != main_photo and not f.startswith(f"{article}")]
                        add_files = add_files[:14]
                        if add_files:
                            book_data["add_photo_urls"] = " ".join([f"{tunnel_url}/vault/{article}/{f}" for f in add_files])

                # 3. Сохраняем книгу в постоянную базу данных SQLite (catalog.db)
                book_data["vault_folder"] = folder_name
                try:
                    save_book_to_db(book_data)
                except Exception as db_err:
                    print(f"⚠️ Ошибка сохранения в SQLite DB: {db_err}")

                # 4. Записываем книгу в Excel
                result = append_book_to_excel(book_data)
                result["saved_photos"] = saved_files
                result["vault_folder"] = folder_name
                result["tunnel_url"] = tunnel_url or ""
                result["main_photo_url"] = book_data.get("main_photo_url", "")
                result["add_photo_urls"] = book_data.get("add_photo_urls", "")
                result["s3_enabled"] = bool(s3_main_url)

                self.send_json(result)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_error_json(e)

        elif parsed.path == "/api/ai_process_photo":
            try:
                body = json.loads(post_data.decode("utf-8"))
                raw_b64 = body.get("image", "")
                if not raw_b64:
                    raise Exception("Нет изображения для обработки")
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                img_bytes = base64.b64decode(raw_b64)
                processed_bytes = process_image_ai(img_bytes)
                out_b64 = "data:image/jpeg;base64," + base64.b64encode(processed_bytes).decode("ascii")
                self.send_json({"success": True, "image": out_b64})
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/save_key":
            try:
                body = json.loads(post_data.decode("utf-8"))
                save_api_key(body.get("key", ""))
                self.send_json({"success": True})
            except Exception as e:
                self.send_error_json(e)


        elif parsed.path == "/api/save_session_draft":
            try:
                with open(DRAFT_FILE, "wb") as f:
                    f.write(post_data)
                self.send_json({"success": True})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)})

        elif parsed.path == "/api/clear_session_draft":
            try:
                if os.path.exists(DRAFT_FILE):
                    os.remove(DRAFT_FILE)
                self.send_json({"success": True})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)})

        elif parsed.path == "/api/clear_excel":
            try:
                body = json.loads(post_data.decode("utf-8")) if post_data else {}
                mode = body.get("mode", "pre2011")
                res = clear_excel_table(mode)
                self.send_json(res)
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/delete_book_row":
            try:
                body = json.loads(post_data.decode("utf-8")) if post_data else {}
                article = body.get("article", "")
                mode = body.get("mode", "pre2011")
                if not article:
                    raise Exception("Не указан артикул книги для удаления")
                try:
                    delete_book_from_db(article)
                except Exception as db_e:
                    print(f"⚠️ Ошибка удаления из БД: {db_e}")
                res = delete_book_from_excel(article, mode)
                self.send_json(res)
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/backup_db":
            try:
                res = backup_db_to_s3()
                self.send_json(res)
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/restore_db":
            try:
                res = restore_db_from_s3()
                self.send_json(res)
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/ozon/save_keys":
            try:
                body = json.loads(post_data.decode("utf-8")) if post_data else {}
                client_id = body.get("client_id", "").strip()
                api_key = body.get("api_key", "").strip()
                if not client_id or not api_key:
                    raise Exception("Необходимо указать Client-Id и Api-Key")
                save_ozon_config(client_id, api_key)
                conn_test = ozon_service.check_ozon_connection()
                self.send_json({"success": True, "connection": conn_test})
            except Exception as e:
                self.send_error_json(e)

        elif parsed.path == "/api/ozon/start_import":
            try:
                res = ozon_service.start_import_catalog_async()
                self.send_json(res)
            except Exception as e:
                self.send_error_json(e)

        else:
            self.send_response(404)
            self.end_headers()

