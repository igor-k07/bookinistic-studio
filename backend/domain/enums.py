"""Domain enumerations for Bookinistic Studio 2.0.

Pure Python stdlib only (ADR-3).
"""

from enum import Enum, IntEnum
from typing import Optional


class PhotoRole(str, Enum):
    """Photo card slot roles according to specifications."""

    COVER_FRONT = "cover_front"         # Slot 1: Front cover
    COVER_BACK = "cover_back"           # Slot 2: Back cover
    INFO_PAGES = "info_pages"           # Slot 3: Title page, colophon, publishing details
    MANTRA_DEFECTS = "mantra_defects"   # Slot 4: Defects, stamps, inscriptions, mantra
    ILLUSTRATIONS = "illustrations"     # Slot 5: Spreads, engravings, illustrations
    OTHER = "other"                     # Additional pages

    @property
    def should_remove_background(self) -> bool:
        """Background removal is permitted strictly for front and back covers."""
        return self in (PhotoRole.COVER_FRONT, PhotoRole.COVER_BACK)

    @property
    def is_ai_vision_candidate(self) -> bool:
        """Only informative photos (covers and info pages) are sent to Gemini Vision."""
        return self in (PhotoRole.COVER_FRONT, PhotoRole.COVER_BACK, PhotoRole.INFO_PAGES)

    @classmethod
    def from_str(cls, val: Optional[str]) -> "PhotoRole":
        """Safe parsing of strings and legacy aliases to PhotoRole."""
        v = (val or "").strip().lower()
        if v in ("cover_front", "cover", "front", "обложка", "лицевая", "slot_1"):
            return cls.COVER_FRONT
        if v in ("cover_back", "back", "задник", "оборот", "slot_2"):
            return cls.COVER_BACK
        if v in (
            "info_pages", "info_page", "title_page", "title", "title_front",
            "colophon", "титул", "титульный", "выходные данные", "slot_3", "info"
        ):
            return cls.INFO_PAGES
        if v in (
            "mantra_defects", "defect", "damage", "mantra", "дефект",
            "повреждение", "нюанс", "мантра", "slot_4", "slot_5"
        ):
            return cls.MANTRA_DEFECTS
        if v in ("illustrations", "illustration", "иллюстрация", "рисунок", "гравюра", "slot_6"):
            return cls.ILLUSTRATIONS
        return cls.OTHER


class BookCondition(str, Enum):
    """Book condition grading according to Ozon marketplace standards."""

    NEW = "Новая"
    FINE = "Как новая"
    VERY_GOOD = "Очень хорошая"
    GOOD = "Хорошая"
    SATISFACTORY = "Удовлетворительная"
    POOR = "Плохая"

    @classmethod
    def from_str(cls, val: Optional[str]) -> "BookCondition":
        """Safe normalization of book condition strings."""
        v = (val or "").strip().lower()
        if "нов" in v and "как" not in v:
            return cls.NEW
        if "как нов" in v or "fine" in v:
            return cls.FINE
        if "очень" in v or "very" in v:
            return cls.VERY_GOOD
        if "удовл" in v or "satisfactory" in v:
            return cls.SATISFACTORY
        if "плох" in v or "poor" in v:
            return cls.POOR
        return cls.GOOD


class AssetStatus(str, Enum):
    """Lifecycle status of a photo asset in the processing pipeline."""

    UPLOADED = "UPLOADED"             # Raw file saved on disk
    AI_PROCESSING = "AI_PROCESSING"   # Background rembg / processing in progress
    READY = "READY"                   # Transform/cutout ready for preview
    S3_SYNCED = "S3_SYNCED"           # Synchronized with Yandex S3
    ARCHIVED = "ARCHIVED"             # Finalized in books_vault/{article}/
    ERROR = "ERROR"                   # Error encountered (retryable)


class BookEra(str, Enum):
    """Ozon category template mode determined by publication year (ADR-4).

    - PRE2011: year <= 2010 or year is None (Bukinistic / Antique, 81 columns, ISBN optional)
    - POST2011: year >= 2011 (Modern editions, 86 columns, ISBN required)
    """

    PRE2011 = "pre2011"
    POST2011 = "post2011"


TemplateMode = BookEra  # Backwards compatibility alias


class OzonSyncStatus(str, Enum):
    """Status of marketplace transactional outbox item."""

    QUEUED = "QUEUED"
    SENDING = "SENDING"
    MODERATION = "MODERATION"
    PUBLISHED = "PUBLISHED"
    ERROR = "ERROR"


class FieldSource(IntEnum):
    """Strict FieldProvenance priority hierarchy (ADR-8).

    Higher values take precedence when merging bibliographic data.
    """

    EMPTY = 0
    DEFAULT = 1
    AI_GEMINI = 2
    DB_CANONICAL = 3
    FANTLAB_EXACT = 4
    USER_MANUAL = 5

