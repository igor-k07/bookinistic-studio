"""Books management, save, validation, reopen, and search router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.domain.models import Book
from backend.presentation.dto import (
    BookDTO,
    CatalogSearchResponse,
    ReopenBookRequest,
    SaveBookRequest,
    ValidateBookRequest,
    WorkspaceTabDTO,
)

router = APIRouter(prefix="/api/books", tags=["Books"])


@router.post("/save")
def save_book(req: SaveBookRequest, request: Request) -> Any:
    """Save book atomically: pre-validation, SQLite, VaultStore, S3 promotion, outbox enqueue."""
    app_state = request.app.state
    save_use_case = app_state.save_book_use_case
    book_domain = Book.from_dict(req.book.model_dump())

    res = save_use_case.execute(
        book=book_domain,
        store_id=req.store_id,
        skip_validation=req.skip_validation,
    )
    if not res.get("success", False):
        raise HTTPException(status_code=400, detail=res.get("errors", "Validation failed"))
    return res


@router.post("/validate")
def validate_book(req: ValidateBookRequest, request: Request) -> Any:
    """Validate book fields against Ozon category rules in ~5 ms."""
    ctx = request.app.state.store_registry.get_active_context()
    book_domain = Book.from_dict(req.book.model_dump())
    errors = (
        ctx.ozon_channel.validate(book_domain)
        if hasattr(ctx.ozon_channel, "validate")
        else ctx.ozon_channel.validate_book(book_domain)
    )
    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/reopen")
def reopen_book(req: ReopenBookRequest, request: Request) -> Any:
    """Reopen cataloged book from DB or Vault manifest into active workspace tab."""
    app_state = request.app.state
    reopen_use_case = app_state.reopen_book_use_case

    try:
        tab = reopen_use_case.execute(req.article)
        ctx = request.app.state.store_registry.get_active_context()
        with ctx.uow:
            book = ctx.book_repo.get_by_article(req.article)
        return {
            "book": book.to_dict() if book else {},
            "tab": WorkspaceTabDTO(
                id=tab.id,
                book_article=tab.book_article,
                tab_order=tab.tab_order,
                is_active=tab.is_active,
                is_edit_mode=tab.is_edit_mode,
                title=tab.title,
                created_at=tab.created_at,
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/catalog", response_model=CatalogSearchResponse)
def search_catalog(request: Request, query: str = "", limit: int = 50, offset: int = 0) -> Any:
    """Search catalog using SQLite FTS5 full-text index (< 2 ms)."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        results = ctx.book_repo.search_fts(query, limit=limit, offset=offset)

    dtos = [BookDTO(**b.to_dict()) for b in results]
    return CatalogSearchResponse(
        books=dtos,
        total=len(dtos),
        query=query,
    )


@router.get("/{article}", response_model=BookDTO)
def get_book(article: str, request: Request) -> Any:
    """Get single book by article."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        book = ctx.book_repo.get_by_article(article)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book {article} not found")
    return BookDTO(**book.to_dict())


@router.delete("/{article}")
def delete_book(article: str, request: Request) -> Any:
    """Delete book and cascade to workspace tabs and outbox."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        deleted = ctx.book_repo.delete(article)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Book {article} not found")
    return {"success": True, "article": article}
