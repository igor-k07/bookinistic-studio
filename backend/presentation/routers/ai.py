"""AI vision recognition and bibliographic enrichment router."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from backend.domain.enums import FieldSource
from backend.domain.models import Book
from backend.domain.rules import classify_filename_to_slot
from backend.presentation.dto import (
    ApplySuggestionRequest,
    BookDTO,
    ClassifyBatchRequest,
    RecognizeRequest,
)

router = APIRouter(prefix="/api/ai", tags=["AI & Enrichment"])


@router.post("/recognize", response_model=BookDTO)
def recognize_book(req: RecognizeRequest, request: Request) -> Any:
    """Run full AI recognition: candidate filtering, barcode lookup, Gemini Vision, and FantLab."""
    use_case = request.app.state.recognize_book_use_case
    book_domain = Book.from_dict(req.book.model_dump())
    # photos format: [[path, role], ...]
    photo_tuples = [(p[0], p[1]) for p in req.photos if len(p) >= 2]

    updated = use_case.execute(book_domain, photo_tuples)
    return BookDTO(**updated.to_dict())


@router.post("/apply-suggestion", response_model=BookDTO)
def apply_suggestion(req: ApplySuggestionRequest, request: Request) -> Any:
    """Apply an AI suggestion or alternative match to the draft book."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        book = ctx.book_repo.get_by_article(req.book_article)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book {req.book_article} not found")

        if hasattr(book, req.field_name):
            setattr(book, req.field_name, req.value)
            book.field_sources[req.field_name] = FieldSource.USER_MANUAL
            ctx.book_repo.save(book)

    return BookDTO(**book.to_dict())


@router.post("/classify-batch")
def classify_batch_photos(req: ClassifyBatchRequest) -> Dict[str, str]:
    """Classify multiple photo filenames into standard slots based on regex/token heuristics."""
    result: Dict[str, str] = {}
    for fn in req.filenames:
        result[fn] = classify_filename_to_slot(fn)
    return result
