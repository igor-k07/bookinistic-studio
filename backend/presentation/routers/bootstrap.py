"""Bootstrap router providing initial state for desktop UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from backend.domain.rules import SOVIET_FORMAT_MAP
from backend.presentation.dto import BootstrapResponse, WorkspaceTabDTO

router = APIRouter(prefix="/api", tags=["Bootstrap"])


@router.get("/bootstrap", response_model=BootstrapResponse)
def get_bootstrap_data(request: Request) -> Any:
    """Return bootstrap payload: active store, references, tabs, and security token."""
    app_state = request.app.state
    registry = app_state.store_registry
    ctx = registry.get_active_context()

    with ctx.uow:
        tabs_raw = ctx.book_repo.list_tabs()
        brands = ctx.reference_repo.search_brands("", limit=100) if ctx.reference_repo else []

    tabs_dto = [
        WorkspaceTabDTO(
            id=t.id,
            book_article=t.book_article,
            tab_order=t.tab_order,
            is_active=t.is_active,
            is_edit_mode=t.is_edit_mode,
            title=t.title,
            created_at=t.created_at,
        )
        for t in tabs_raw
    ]

    token = app_state.token_manager.get_token() if hasattr(app_state, "token_manager") else ""
    tunnel_url = (
        app_state.tunnel_manager.tunnel_url
        if hasattr(app_state, "tunnel_manager")
        else None
    )

    return BootstrapResponse(
        stores=[s.to_dict() for s in registry.list_stores()],
        active_store=registry.active_store_id,
        brands=brands,
        gost_formats=SOVIET_FORMAT_MAP,
        tabs=tabs_dto,
        mobile_token=token,
        tunnel_url=tunnel_url,
    )
