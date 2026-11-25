"""Recognize Book Use Case.

Coordinates vision recognition, local barcode lookups, FantLab enrichment,
strict FieldProvenance merge rules (never overwriting USER_MANUAL), and reference brand normalization.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.domain.enums import FieldSource, PhotoRole
from backend.domain.models import Book
from backend.domain.ports import (
    IAIVisionClient,
    IBookRepository,
    IEnrichmentClient,
    IEventBroker,
    IReferenceRepository,
)
from backend.domain.rules import merge_field_value

logger = logging.getLogger(__name__)


class RecognizeBookUseCase:
    """Use case orchestrating AI recognition, external enrichment, and provenance-safe merging."""

    def __init__(
        self,
        book_repo: IBookRepository,
        ai_client: IAIVisionClient,
        enrichment_client: IEnrichmentClient,
        reference_repo: Optional[IReferenceRepository] = None,
        event_broker: Optional[IEventBroker] = None,
    ) -> None:
        self.book_repo = book_repo
        self.ai_client = ai_client
        self.enrichment_client = enrichment_client
        self.reference_repo = reference_repo
        self.event_broker = event_broker

    def execute(
        self,
        book: Book,
        photos: List[Tuple[str, str]],  # List of (image_path, role_string)
    ) -> Book:
        """Run end-to-end recognition pipeline on the given book."""
        self._notify_progress(book.article, 0.1, "Filtering candidate images...")

        # 1. Strict PhotoRole.is_ai_vision_candidate filter
        candidate_paths: List[str] = []
        for path, role_str in photos:
            role = PhotoRole.from_str(role_str)
            if role.is_ai_vision_candidate:
                candidate_paths.append(path)

        if not candidate_paths:
            logger.warning("No candidate photos found for vision recognition")
            self._notify_progress(book.article, 1.0, "No candidate photos")
            return book

        # 2. Local Barcode DB lookup
        if book.barcode:
            self._notify_progress(book.article, 0.2, "Checking local catalog for barcode...")
            existing_books = self.book_repo.search_fts(book.barcode, limit=1)
            if existing_books:
                existing = existing_books[0]
                self._merge_authoritative_book(book, existing, FieldSource.DB_CANONICAL)
                self._notify_progress(book.article, 1.0, "Matched from local catalog")
                return book

        # 3. Gemini Vision 1200px recognition
        self._notify_progress(book.article, 0.4, "Querying Gemini Vision AI...")
        ai_data = self.ai_client.recognize_images(candidate_paths)

        # Merge raw AI fields into Book using AI_GEMINI provenance
        self._apply_ai_data_to_book(book, ai_data)

        # 4. External Enrichment (FantLab / OpenLibrary)
        self._notify_progress(book.article, 0.7, "Searching bibliographic databases...")
        candidates = self.enrichment_client.search_candidates(
            title=book.title,
            author=book.author,
            year=book.year,
            isbn=book.isbn or None,
        )

        exact_candidate = next((c for c in candidates if c.exact_match), None)
        if exact_candidate:
            # Authoritative exact match: apply fields with FANTLAB_EXACT priority
            for field_name, val in exact_candidate.fields.items():
                if hasattr(book, field_name) and val:
                    curr_val = getattr(book, field_name)
                    merged, new_src = merge_field_value(
                        field_name=field_name,
                        current_value=curr_val,
                        current_source=book.field_sources.get(field_name, FieldSource.EMPTY),
                        incoming_value=val,
                        incoming_source=FieldSource.FANTLAB_EXACT,
                    )
                    setattr(book, field_name, merged)
                    book.field_sources[field_name] = new_src
        else:
            # Fuzzy match candidates: store non-destructively in suggestions
            book.suggestions["candidates"] = [c.fields for c in candidates]

        # 5. Reference brand normalization
        if self.reference_repo and book.publisher:
            if self.reference_repo.is_known_brand(book.publisher):
                book.brand = book.publisher
            else:
                brands = self.reference_repo.search_brands(book.publisher, limit=1)
                if brands:
                    book.brand = brands[0]

        self._notify_progress(book.article, 1.0, "Recognition complete")
        return book

    def _apply_ai_data_to_book(self, book: Book, ai_data: Dict[str, Any]) -> None:
        """Merge fields returned by Gemini Vision with AI_GEMINI provenance."""
        for field_name in (
            "title", "author", "year", "publisher", "isbn",
            "annotation", "pages", "cover_type", "genre",
            "condition", "age_limit", "translator", "illustrator",
        ):
            if field_name in ai_data and ai_data[field_name]:
                val = ai_data[field_name]
                curr_val = getattr(book, field_name, None)
                merged, new_src = merge_field_value(
                    field_name=field_name,
                    current_value=curr_val,
                    current_source=book.field_sources.get(field_name, FieldSource.EMPTY),
                    incoming_value=val,
                    incoming_source=FieldSource.AI_GEMINI,
                )
                setattr(book, field_name, merged)
                book.field_sources[field_name] = new_src

    def _merge_authoritative_book(self, target: Book, source: Book, source_type: FieldSource) -> None:
        """Merge fields from an existing authoritative book."""
        for field_name in ("title", "author", "year", "publisher", "isbn", "pages", "brand"):
            src_val = getattr(source, field_name, None)
            if src_val:
                curr_val = getattr(target, field_name, None)
                merged, new_src = merge_field_value(
                    field_name=field_name,
                    current_value=curr_val,
                    current_source=target.field_sources.get(field_name, FieldSource.EMPTY),
                    incoming_value=src_val,
                    incoming_source=source_type,
                )
                setattr(target, field_name, merged)
                target.field_sources[field_name] = new_src

    def _notify_progress(self, article: str, progress: float, message: str) -> None:
        if self.event_broker:
            try:
                self.event_broker.publish(
                    "ai.progress",
                    {"article": article, "progress": progress, "message": message},
                )
            except Exception as e:
                logger.warning("Failed to publish AI progress: %s", e)
