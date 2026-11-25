"""Application layer use cases.

Strictly program to domain interfaces (backend.domain.ports).
Zero external framework or concrete persistence dependencies.
"""

from backend.application.use_cases.asset_pipeline import AssetPipelineUseCase
from backend.application.use_cases.cleanup_storage import CleanupStorageUseCase
from backend.application.use_cases.recognize_book import RecognizeBookUseCase
from backend.application.use_cases.reopen_book import ReopenBookUseCase
from backend.application.use_cases.save_book import SaveBookUseCase
from backend.application.use_cases.sync_catalog import SyncCatalogUseCase

__all__ = [
    "AssetPipelineUseCase",
    "RecognizeBookUseCase",
    "SaveBookUseCase",
    "ReopenBookUseCase",
    "SyncCatalogUseCase",
    "CleanupStorageUseCase",
]

