"""
app.py: Точка входа сервера Bookinistic Studio.
Запуск локального многопоточного веб-сервера для пакетной каталогизации книг для Ozon.
"""

import os
import sys
from http.server import ThreadingHTTPServer

from config import PORT, get_target_excel_file
from server.handler import BatchHandler
from services.db_service import init_db
import services.tunnel_service as tunnel_service


def run_server():
    init_db()
    server_address = ("", PORT)
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(server_address, BatchHandler)

    print("=" * 65)
    print(f" 📚 Bookinistic Batch Studio запущена на порту {PORT}!")
    print(f" 👉 Десктоп: http://localhost:{PORT}")
    print(f" 📱 Мобильный: http://localhost:{PORT}/mobile")

    # Запуск туннеля и сетевого мониторинга
    print(f" 🚀 Запуск Cloudflare Tunnel для порта {PORT}...", flush=True)
    tunnel_url = tunnel_service.start_tunnel(PORT)
    tunnel_service.start_network_watchdog(PORT)

    if tunnel_url:
        print(f" 🌟 Cloudflare Tunnel активен: {tunnel_url}")
    else:
        print(" ℹ️ Cloudflare Tunnel не запустился (доступен локальный режим)")

    pre_file = os.path.basename(get_target_excel_file("pre2011"))
    post_file = os.path.basename(get_target_excel_file("post2011"))
    print(f" 📊 Актуальные таблицы: {pre_file} | {post_file}")
    print(" Для остановки нажмите Ctrl + C в терминале")
    print("=" * 65, flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Завершение работы Bookinistic Studio...", flush=True)
    finally:
        tunnel_service.stop_tunnel()
        httpd.server_close()
        print("✅ Сервер успешно остановлен.", flush=True)


if __name__ == "__main__":
    run_server()
