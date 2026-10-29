"""
tunnel_service.py: Управление Cloudflare Quick Tunnel и мониторинг сетевого подключения.
"""

from typing import Optional
import tunnel_manager


def get_tunnel_url() -> Optional[str]:
    """Возвращает текущий активный публичный HTTPS URL туннеля."""
    return tunnel_manager.get_tunnel_url()


def get_local_url(port: int = 8095) -> str:
    """Возвращает локальный URL в Wi-Fi сети для мобильного подключения."""
    return tunnel_manager.get_local_url(port)


def get_local_ip() -> str:
    """Возвращает локальный IP компьютера в сети."""
    return tunnel_manager.get_local_ip()


def start_tunnel(port: int = 8095) -> Optional[str]:
    """Запускает Cloudflare Quick Tunnel на указанный порт."""
    return tunnel_manager.start_tunnel(port)


def stop_tunnel() -> None:
    """Останавливает Cloudflare Quick Tunnel."""
    tunnel_manager.stop_tunnel()


def restart_tunnel(port: int = 8095) -> Optional[str]:
    """Перезапускает Cloudflare Quick Tunnel."""
    return tunnel_manager.restart_tunnel(port)


def start_network_watchdog(port: int = 8095) -> None:
    """Запускает фоновый мониторинг сети и автоперезапуск туннеля."""
    tunnel_manager.start_network_watchdog(port)

