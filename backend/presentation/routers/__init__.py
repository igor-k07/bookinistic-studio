"""Presentation layer API routers."""

from backend.presentation.routers.ai import router as ai_router
from backend.presentation.routers.assets import router as assets_router
from backend.presentation.routers.books import router as books_router
from backend.presentation.routers.bootstrap import router as bootstrap_router
from backend.presentation.routers.events import router as events_router
from backend.presentation.routers.mobile import router as mobile_router
from backend.presentation.routers.ozon import router as ozon_router
from backend.presentation.routers.proxy import router as proxy_router
from backend.presentation.routers.system import router as system_router
from backend.presentation.routers.tabs import router as tabs_router

__all__ = [
    "ai_router",
    "assets_router",
    "books_router",
    "bootstrap_router",
    "events_router",
    "mobile_router",
    "ozon_router",
    "proxy_router",
    "system_router",
    "tabs_router",
]
