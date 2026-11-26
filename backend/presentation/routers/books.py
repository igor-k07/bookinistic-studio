"""Books management, save, validation, reopen, and search router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.domain.exceptions import ValidationError
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


@router.get("/next-article")
def get_next_article(request: Request) -> Any:
    """Return next sequential DP-B-XXXXX article number."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        article = ctx.book_repo.next_article()
    return {"article": article}


@router.get("/excel-preview")
def get_excel_preview(request: Request, mode: str = "pre2011") -> Any:
    """Return non-draft books grouped by era for the embedded Excel preview table."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        all_books = ctx.book_repo.search_fts("", limit=5000, offset=0)

    pre_books = []
    post_books = []
    for b in all_books:
        if (b.status or "").upper() == "DRAFT":
            continue
        if b.year and b.year >= 2011:
            post_books.append(b)
        else:
            pre_books.append(b)

    selected = post_books if mode == "post2011" else pre_books
    return {
        "mode": mode,
        "books": [BookDTO(**b.to_dict()) for b in selected[:200]],
        "pre2011_count": len(pre_books),
        "post2011_count": len(post_books),
        "total": len(pre_books) + len(post_books),
    }


@router.post("/clear-excel")
def clear_excel_tables(request: Request, mode: str = "pre2011") -> Any:
    """Backup and reset Excel export table(s) to clean Ozon template."""
    exporter = getattr(request.app.state, "excel_exporter", None)
    if not exporter:
        raise HTTPException(status_code=500, detail="Excel exporter not configured")
    return exporter.clear_table(mode)


@router.post("/save")
def save_book(req: SaveBookRequest, request: Request) -> Any:
    """Save book atomically: pre-validation, SQLite, VaultStore, S3 promotion, outbox enqueue."""
    app_state = request.app.state
    save_use_case = app_state.save_book_use_case
    registry = app_state.store_registry
    store_id = req.store_id if req.store_id and req.store_id != "default" else registry.active_store_id
    book_domain = Book.from_dict(req.book.model_dump())

    try:
        res = save_use_case.execute(
            book=book_domain,
            store_id=store_id,
            skip_validation=req.skip_validation,
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    """Delete book from SQLite and Excel catalog."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        deleted = ctx.book_repo.delete(article)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Book {article} not found")
    exporter = getattr(request.app.state, "excel_exporter", None)
    if exporter:
        try:
            exporter.remove_book(article)
        except Exception:
            pass
    return {"success": True, "article": article}
