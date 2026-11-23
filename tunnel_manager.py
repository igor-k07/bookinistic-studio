"""
tunnel_manager.py: Обратная совместимость для services/tunnel_service.py.
Все управление Cloudflare Quick Tunnel перенесено в services.tunnel_service.
"""

from services.tunnel_service import (
    BIN_PATH,
    cleanup_stale_tunnels,
    get_local_ip,
    get_local_url,
    get_tunnel_url,
    is_vpn_active,
    restart_tunnel,
    start_network_watchdog,
    start_tunnel,
    stop_tunnel,
)

__all__ = [
    "BIN_PATH",
    "cleanup_stale_tunnels",
    "get_local_ip",
    "get_local_url",
    "get_tunnel_url",
    "is_vpn_active",
    "restart_tunnel",
    "start_network_watchdog",
    "start_tunnel",
    "stop_tunnel",
]
