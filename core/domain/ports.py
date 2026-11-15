"""
ports.py: Порты (интерфейсы) Чистой Архитектуры для Bookinistic Studio.
Определяют контракты взаимодействия ядра со внешними сервисами, БД и файлами.
Реализации (адаптеры) находятся в слое infrastructure/.
"""

from typing import Any, Dict, List, Optional, Protocol, Tuple

from core.domain.enums import PhotoRole
from core.domain.models import Book


class IBookRepository(Protocol):
    """Порт доступа к базе данных каталога книг."""
    def save(self, book: Book) -> Book: ...
    def get_by_article(self, article: str) -> Optional[Book]: ...
    def delete(self, article: str) -> bool: ...
    def list_books(
        self,
        mode: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Book]: ...
    def get_next_article(self) -> str: ...


class IMediaStorage(Protocol):
    """Порт постоянного или облачного хранилища медиа-файлов (S3 / Tunnel / Vault)."""
    def upload_book_photos(
        self,
        article: str,
        title: str,
        slots_photos: Dict[str, Any],
    ) -> Tuple[Optional[str], str]:
        """Возвращает (main_photo_url, add_photo_urls)."""
        ...


class ICatalogExporter(Protocol):
    """Порт экспорта каталога (Excel OpenXML или Ozon Seller API)."""
    def append_book(self, book: Book) -> Dict[str, Any]: ...
    def delete_book(self, article: str, mode: str) -> Dict[str, Any]: ...
    def clear(self, mode: str) -> Dict[str, Any]: ...


class IAIClient(Protocol):
    """Порт взаимодействия с ИИ (Gemini Vision и классификатор)."""
    def recognize_book(self, images: List[Dict[str, Any]], api_key: str) -> Dict[str, Any]: ...
    def classify_and_group(self, photos: List[Dict[str, Any]], api_key: str) -> List[Dict[str, Any]]: ...


class IImageProcessor(Protocol):
    """Порт обработки изображений (rembg, поворот, кадрирование)."""
    def process(self, image_bytes: bytes, role: PhotoRole) -> Dict[str, Any]: ...

