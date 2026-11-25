"""Domain exceptions for Bookinistic Studio 2.0.

Pure Python stdlib only (ADR-3).
"""

from typing import Any, Dict, Optional


class DomainError(Exception):
    """Base exception for all domain logic violations."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(DomainError):
    """Raised when an entity or value object fails business rule validation."""
    pass


class ArticleConflictError(DomainError):
    """Raised when an article already exists or violates sequence allocation."""
    pass


class ConcurrencyError(DomainError):
    """Raised when an optimistic lock conflict occurs (e.g. Asset version mismatch)."""
    pass


class ResourceNotFoundError(DomainError):
    """Raised when a requested domain entity (book, asset, tab) cannot be found."""
    pass


EntityNotFoundError = ResourceNotFoundError


class StorageError(DomainError):
    """Raised when media, vault, or cloud storage operations fail."""
    pass


class AuthenticationError(DomainError):
    """Raised when external API authentication fails (e.g. invalid API key)."""
    pass


class ExternalServiceError(DomainError):
    """Raised when external service (AI vision, enrichment, marketplace) fails."""
    pass



