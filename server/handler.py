"""
handler.py: HTTP обработчик запросов BatchHandler для Bookinistic Studio.
Архитектура: Тонкий адаптер HTTP-транспорта, делегирующий маршрутизацию в Router,
а бизнес-логику — в Use Cases и контроллеры.
"""

import http.server
import json
import os
import socket
import time
from typing import Any
import urllib.parse

from config import (
    BASE_DIR,
    INBOX_DIR,
    SESSION_PHOTOS_DIR,
    TEMPLATES_DIR,
    VAULT_DIR,
    get_card_image_path,
)
from server.routes import build_router

# Инициализируем глобальный роутер приложения один раз
ROUTER = build_router()


class BatchHandler(http.server.BaseHTTPRequestHandler):
    """Основной HTTP обработчик веб-интерфейса и REST API."""

    def setup(self):
        super().setup()
        try:
            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

    def log_message(self, format, *args):
        # Отключаем стандартный спам логов в терминал
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

    def _serve_file_stream(self, full_file_path: str, tag: str = "STATIC", rel_label: str = ""):
        """Потоковая отдача статического медиафайла (картинки) с авто-определением mime-типа."""
        if os.path.exists(full_file_path) and os.path.isfile(full_file_path):
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
            if tag == "SESSION_PHOTO" or "session_photos" in full_file_path:
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            else:
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
            if t_spent > 0.5:
                print(f"📸 [{tag}] 200 OK ({file_size // 1024} KB in {t_spent:.2f}s) -> {rel_label}", flush=True)
        else:
            self.send_response(404)
            self.end_headers()

    # -------------------------------------------------------------
    # GET ЗАПРОСЫ
    # -------------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. HTML-страницы
        if path == "/":
            self.serve_template("desktop.html")
            return
        if path == "/mobile":
            self.serve_template("mobile.html")
            return

        # 2. Постоянная карточка магазина
        if path in ("/card.png", "/templates/card.png", "/storage/card.png"):
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
            return

        # 3. Фото сессии
        if path.startswith("/session_photos/"):
            rel_path = urllib.parse.unquote(path[len("/session_photos/"):])
            safe_rel_path = os.path.normpath(rel_path).lstrip("/\\")
            if safe_rel_path.startswith(".."):
                self.send_response(403)
                self.end_headers()
                return
            full_file_path = os.path.join(SESSION_PHOTOS_DIR, safe_rel_path)
            if not (os.path.exists(full_file_path) and os.path.isfile(full_file_path)):
                # Защита от 404: если временный файл сессии отсутствует, ищем в архиве books_vault
                fname = os.path.basename(safe_rel_path)
                m = re.search(r"(photo_[a-z0-9]+)", fname)
                prefix = m.group(1) if m else fname.split(".")[0]
                if os.path.exists(VAULT_DIR):
                    for d in os.listdir(VAULT_DIR):
                        v_dir = os.path.join(VAULT_DIR, d)
                        if os.path.isdir(v_dir):
                            bs_file = os.path.join(v_dir, "book_state.json")
                            if os.path.exists(bs_file):
                                try:
                                    with open(bs_file, "r", encoding="utf-8") as f_bs:
                                        if prefix in f_bs.read():
                                            cand = os.path.join(v_dir, "01_cover_front.jpg")
                                            if os.path.exists(cand):
                                                full_file_path = cand
                                                break
                                except Exception:
                                    pass
            self._serve_file_stream(full_file_path, tag="SESSION_PHOTO", rel_label=safe_rel_path)
            return

        # 3.1. Ассеты V2 (GET /api/assets/<id>/preview и GET /api/assets/<id>/full)
        if path.startswith("/api/assets/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 4 and parts[0] == "api" and parts[1] == "assets":
                asset_id = parts[2]
                variant = parts[3]
                import services.asset_service as asset_service
                asset = asset_service.get_asset(asset_id)
                if asset:
                    file_to_serve = None
                    if variant == "preview" and os.path.exists(asset.preview_path):
                        file_to_serve = asset.preview_path
                    elif variant == "full":
                        if asset.ai_white_path and os.path.exists(asset.ai_white_path):
                            file_to_serve = asset.ai_white_path
                        elif os.path.exists(asset.original_path):
                            file_to_serve = asset.original_path
                    if file_to_serve and os.path.exists(file_to_serve):
                        self._serve_file_stream(file_to_serve, tag="ASSET_V2", rel_label=f"{asset_id}_{variant}")
                        return

        # 4. Фото из архива books_vault/
        if path.startswith("/vault/"):
            rel_path = urllib.parse.unquote(path[len("/vault/"):])
            safe_rel_path = os.path.normpath(rel_path).lstrip("/\\")
            if safe_rel_path.startswith(".."):
                self.send_response(403)
                self.end_headers()
                return

            full_file_path = os.path.join(VAULT_DIR, safe_rel_path)
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

            self._serve_file_stream(full_file_path, tag="VAULT", rel_label=safe_rel_path)
            return

        # 5. Inbox (фото с мобильного)
        if path.startswith("/inbox/"):
            rel_path = urllib.parse.unquote(path[len("/inbox/"):])
            safe_rel_path = os.path.normpath(rel_path).lstrip("/\\")
            if safe_rel_path.startswith(".."):
                self.send_response(403)
                self.end_headers()
                return
            full_file_path = os.path.join(INBOX_DIR, safe_rel_path)
            self._serve_file_stream(full_file_path, tag="INBOX", rel_label=safe_rel_path)
            return

        # 5.1. Безопасный CORS-прокси для внешних облачных изображений (S3, Ozon CDN)
        # Позволяет Cropper.js и HTML5 Canvas обрабатывать фото без блокировок браузера
        if path == "/api/image_proxy":
            query = urllib.parse.parse_qs(parsed.query)
            target_url = (query.get("url") or [""])[0].strip()
            if not target_url or not (target_url.startswith("http://") or target_url.startswith("https://")):
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b"Param 'url' must be valid http/https URL")
                return

            try:
                import requests
                # Нормализация URL: кодируем кириллицу и спецсимволы в path и query
                p_parts = urllib.parse.urlsplit(target_url)
                ascii_path = urllib.parse.quote(urllib.parse.unquote(p_parts.path), safe="/:@&=+$,-_.!~*'()")
                ascii_query = urllib.parse.quote(urllib.parse.unquote(p_parts.query), safe="/:@&=+$,-_.!~*'()")
                ascii_url = urllib.parse.urlunsplit((p_parts.scheme, p_parts.netloc, ascii_path, ascii_query, p_parts.fragment))

                r = requests.get(ascii_url, headers={"User-Agent": "BookinisticProxy/1.0"}, timeout=15)
                if r.status_code == 200:
                    c_type = r.headers.get("Content-Type") or "image/jpeg"
                    img_bytes = r.content
                    self.send_response(200)
                    self.send_header("Content-Type", c_type)
                    self.send_header("Content-Length", str(len(img_bytes)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(img_bytes)
                else:
                    self.send_response(r.status_code)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
            except Exception as e_proxy:
                print(f"⚠️ Ошибка image_proxy для {target_url}: {e_proxy}")
                self.send_response(502)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
            return

        # 6. Статика (JS, CSS, шрифты)
        if (path.startswith("/static/") or path.endswith((".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".webp"))) and not path.startswith(("/session_photos/", "/vault/", "/inbox/")):
            clean_rel = urllib.parse.unquote(path.lstrip("/"))
            candidates = [
                os.path.join(TEMPLATES_DIR, clean_rel),
                os.path.join(TEMPLATES_DIR, os.path.basename(clean_rel)),
                os.path.join(TEMPLATES_DIR, "static", os.path.basename(clean_rel)),
                os.path.join(BASE_DIR, clean_rel),
            ]
            full_file_path = None
            for cand in candidates:
                if os.path.exists(cand) and os.path.isfile(cand):
                    full_file_path = cand
                    break

            if full_file_path:
                ext = os.path.splitext(full_file_path)[1].lower()
                mime_map = {
                    ".js": "application/javascript; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".svg": "image/svg+xml",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".json": "application/json; charset=utf-8",
                }
                content_type = mime_map.get(ext, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                if self.command != "HEAD":
                    with open(full_file_path, "rb") as f:
                        while True:
                            chunk = f.read(262144)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        # 7. Диспетчеризация через Router
        if ROUTER.dispatch(self, "GET"):
            return

        # 404 если маршрут не найден
        self.send_response(404)
        self.end_headers()

    # -------------------------------------------------------------
    # POST ЗАПРОСЫ
    # -------------------------------------------------------------
    def do_POST(self):
        # Вся обработка POST делегируется декларативному Router
        if ROUTER.dispatch(self, "POST"):
            return

        self.send_response(404)
        self.end_headers()
