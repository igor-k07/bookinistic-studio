"""Workspace tabs management router."""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, HTTPException, Request

from backend.domain.models import Book, WorkspaceTab
from backend.presentation.dto import WorkspaceTabDTO

router = APIRouter(prefix="/api/tabs", tags=["Workspace Tabs"])


@router.get("", response_model=List[WorkspaceTabDTO])
def list_workspace_tabs(request: Request) -> Any:
    """List all open workspace tabs."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        tabs = ctx.book_repo.list_tabs()
    return [
        WorkspaceTabDTO(
            id=t.id,
            book_article=t.book_article,
            tab_order=t.tab_order,
            is_active=t.is_active,
            is_edit_mode=t.is_edit_mode,
            title=t.title,
            created_at=t.created_at,
        )
        for t in tabs
    ]


@router.post("", response_model=WorkspaceTabDTO)
def create_workspace_tab(tab_dto: WorkspaceTabDTO, request: Request) -> Any:
    """Open or create a new workspace tab."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        # ADR-9: Ensure draft book row exists in books table to satisfy FK constraint
        if not ctx.book_repo.get_by_article(tab_dto.book_article):
            draft_book = Book(
                article=tab_dto.book_article,
                title=tab_dto.title or tab_dto.book_article,
                status="DRAFT",
            )
            ctx.book_repo.save(draft_book)

        tab = WorkspaceTab(
            id=tab_dto.id,
            book_article=tab_dto.book_article,
            tab_order=tab_dto.tab_order,
            is_active=tab_dto.is_active,
            is_edit_mode=tab_dto.is_edit_mode,
            title=tab_dto.title,
        )
        ctx.book_repo.save_tab(tab)
    return tab_dto


@router.patch("/{tab_id}", response_model=WorkspaceTabDTO)
def update_workspace_tab(tab_id: str, updates: dict, request: Request) -> Any:
    """Update active state or order of a tab."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        tabs = ctx.book_repo.list_tabs()
        tab = next((t for t in tabs if t.id == tab_id), None)
        if not tab:
            raise HTTPException(status_code=404, detail=f"Tab {tab_id} not found")

        if "is_active" in updates:
            tab.is_active = bool(updates["is_active"])
        if "is_edit_mode" in updates:
            tab.is_edit_mode = bool(updates["is_edit_mode"])
        if "tab_order" in updates:
            tab.tab_order = int(updates["tab_order"])

        ctx.book_repo.save_tab(tab)

    return WorkspaceTabDTO(
        id=tab.id,
        book_article=tab.book_article,
        tab_order=tab.tab_order,
        is_active=tab.is_active,
        is_edit_mode=tab.is_edit_mode,
        title=tab.title,
        created_at=tab.created_at,
    )


@router.delete("/{tab_id}")
def delete_workspace_tab(tab_id: str, request: Request) -> Any:
    """Close a workspace tab."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        deleted = ctx.book_repo.delete_tab(tab_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tab {tab_id} not found")
    return {"success": True, "tab_id": tab_id}
