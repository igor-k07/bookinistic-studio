"""
tunnel_manager.py: Управление Cloudflare Quick Tunnel для бесшовной мобильной загрузки со смартфона и отдачи фото для Ozon.
"""

import os
import re
import socket
import subprocess
import threading
import time
from typing import Optional

BIN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared")
_tunnel_proc: Optional[subprocess.Popen] = None
_tunnel_url: Optional[str] = None
_lock = threading.Lock()


def get_tunnel_url() -> Optional[str]:
    global _tunnel_proc, _tunnel_url
    with _lock:
        if _tunnel_proc and _tunnel_proc.poll() is not None:
            _tunnel_proc = None
            _tunnel_url = None
        return _tunnel_url


def get_local_ip() -> str:
    """Определяет локальный IP-адрес в Wi-Fi сети."""
    for iface in ("en0", "en1", "en2"):
        try:
            out = subprocess.check_output(["ipconfig", "getifaddr", iface], text=True).strip()
            if out:
                return out
        except Exception:
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def is_vpn_active() -> bool:
    """Проверяет, включен ли VPN на Mac (наличие активного utun интерфейса в маршрутах)."""
    try:
        out = subprocess.check_output(["netstat", "-rn"], text=True)
        return any("utun" in line and "default" in line for line in out.splitlines())
    except Exception:
        return False


def get_local_url(port: int = 8090) -> str:
    ip = get_local_ip()
    return f"http://{ip}:{port}"


def cleanup_stale_tunnels():
    """Гарантированно завершает любые оставшиеся процессы cloudflared."""
    try:
        subprocess.run(["pkill", "-9", "-f", "cloudflared tunnel"], capture_output=True)
    except Exception:
        pass


def start_tunnel(port: int = 8090) -> Optional[str]:
    """
    Запускает фоновый Cloudflare Quick Tunnel на указанный порт и извлекает публичный HTTPS-адрес.
    """
    global _tunnel_proc, _tunnel_url

    with _lock:
        if _tunnel_url and _tunnel_proc and _tunnel_proc.poll() is None:
            return _tunnel_url

        if not os.path.exists(BIN_PATH):
            print("cloudflared binary not found at", BIN_PATH)
            return None

        # Завершаем старые зомби-процессы туннеля, чтобы избежать конфликтов Cloudflare
        cleanup_stale_tunnels()
        time.sleep(0.4)

        print(f"🚀 Запуск Cloudflare Tunnel для порта {port}...")
        _tunnel_proc = subprocess.Popen(
            [BIN_PATH, "tunnel", "--edge-ip-version", "4", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )

        found_url = None
        t0 = time.time()

        def read_stream():
            nonlocal found_url
            try:
                for line in _tunnel_proc.stderr:
                    line_s = line.strip()
                    if not found_url:
                        match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line_s)
                        if match:
                            found_url = match.group(0)
                            with _lock:
                                global _tunnel_url
                                _tunnel_url = found_url
                            print(f"🌟 Cloudflare Tunnel активен: {found_url}", flush=True)
                    if any(w in line_s.lower() for w in ["connindex", "registered", "error", "fail", "unregistered", "retrying"]):
                        print(f"[cloudflared] {line_s}", flush=True)
            except Exception:
                pass

        th = threading.Thread(target=read_stream, daemon=True)
        th.start()

        # Ждем появления адреса до 15 секунд
        while time.time() - t0 < 15:
            if found_url:
                break
            time.sleep(0.3)

        return found_url


def stop_tunnel():
    """Останавливает процесс туннеля."""
    global _tunnel_proc, _tunnel_url
    with _lock:
        if _tunnel_proc:
            try:
                _tunnel_proc.terminate()
                _tunnel_proc.wait(timeout=2)
            except Exception:
                try:
                    _tunnel_proc.kill()
                except Exception:
                    pass
            _tunnel_proc = None
        cleanup_stale_tunnels()
        _tunnel_url = None


def restart_tunnel(port: int = 8090) -> Optional[str]:
    """Принудительно перезапускает туннель (при смене сети Wi-Fi или обрыве)."""
    stop_tunnel()
    time.sleep(0.5)
    return start_tunnel(port)


_watchdog_started = False


def start_network_watchdog(port: int = 8090):
    """
    Фоновый страж: отслеживает смену Wi-Fi сети (смену локального IP)
    или падение процесса cloudflared и автоматически восстанавливает соединение.
    """
    global _watchdog_started
    if _watchdog_started:
        return
    _watchdog_started = True

    def watchdog_loop():
        last_ip = get_local_ip()
        while True:
            time.sleep(4)
            try:
                curr_ip = get_local_ip()
                # 1. Если сменился локальный IP (переключение на другой роутер/точку доступа)
                if curr_ip != "127.0.0.1" and last_ip != "127.0.0.1" and curr_ip != last_ip:
                    print(f"🔄 Смена Wi-Fi сети: {last_ip} -> {curr_ip}. Автоперезапуск Cloudflare Tunnel...")
                    last_ip = curr_ip
                    restart_tunnel(port)
                    continue

                last_ip = curr_ip

                # 2. Если процесс cloudflared неожиданно завершился
                with _lock:
                    proc_died = _tunnel_proc is not None and _tunnel_proc.poll() is not None

                if proc_died:
                    print("⚠️ Cloudflare Tunnel завершился. Автоматический перезапуск...")
                    restart_tunnel(port)

            except Exception:
                pass

    t = threading.Thread(target=watchdog_loop, daemon=True)
    t.start()


