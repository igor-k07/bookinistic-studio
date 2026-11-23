"""
enums.py: Доменные перечисления для Bookinistic Studio.
Определяет роли фотографий, состояния книг и режимы шаблонов Ozon.
"""

from enum import Enum


class PhotoRole(str, Enum):
    """
    Роли фотографий в карточке книги согласно спецификации.
    """
    COVER_FRONT = "cover_front"         # Лицевая обложка (слот 1)
    COVER_BACK = "cover_back"           # Задняя обложка (слот 2)
    TITLE_PAGE = "title_page"           # Титульный лист (слот 3)
    COLOPHON = "colophon"               # Выходные данные / мантра (слот 4)
    DEFECT = "defect"                   # Фото дефекта/повреждения (слот 5)
    ILLUSTRATION = "illustration"       # Иллюстрация/разворот (слот 6)
    OTHER = "other"                     # Дополнительные страницы

    @property
    def should_remove_background(self) -> bool:
        """
        Согласно п. 3.2 спецификации:
        - Лицевая обложка и задник: удаление фона стола (#FFFFFF).
        - Титулы, текст, мантры, дефекты и иллюстрации: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО удалять фон.
        """
        return self in (PhotoRole.COVER_FRONT, PhotoRole.COVER_BACK)

    @property
    def is_ai_vision_candidate(self) -> bool:
        """
        Согласно п. 4.1 спецификации:
        В Gemini Vision отправляются СТРОГО информационные фото (обложка, титулы, колофон).
        Иллюстрации и дефекты в Gemini не отправляются.
        """
        return self in (
            PhotoRole.COVER_FRONT,
            PhotoRole.COVER_BACK,
            PhotoRole.TITLE_PAGE,
            PhotoRole.COLOPHON,
        )

    @classmethod
    def from_str(cls, val: str) -> "PhotoRole":
        """Безопасное преобразование строкового имени роли или слота."""
        v = (val or "").strip().lower()
        if v in ("cover_front", "cover", "front", "обложка", "лицевая", "slot_1"):
            return cls.COVER_FRONT
        if v in ("cover_back", "back", "задник", "оборот", "slot_2"):
            return cls.COVER_BACK
        if v in ("title_page", "title", "title_front", "титул", "титульный", "slot_3"):
            return cls.TITLE_PAGE
        if v in ("colophon", "mantra", "колофон", "мантра", "выходные данные", "slot_4"):
            return cls.COLOPHON
        if v in ("defect", "damage", "дефект", "повреждение", "нюанс", "slot_5"):
            return cls.DEFECT
        if v in ("illustration", "иллюстрация", "рисунок", "гравюра", "slot_6"):
            return cls.ILLUSTRATION
        return cls.OTHER


class BookCondition(str, Enum):
    """
    Градации сохранности книги по регламенту Ozon (п. 5.3 спецификации).
    """
    VERY_GOOD = "Очень хорошая"
    GOOD = "Хорошая"
    SATISFACTORY = "Удовлетворительная"
    BAD = "Плохая"


class AssetStatus(str, Enum):
    """
    Статусы жизненного цикла ассета (фотокадра) в конвейере.
    """
    UPLOADED = "UPLOADED"             # Сырой оригинал загружен на диск
    AI_PROCESSING = "AI_PROCESSING"   # rembg / вырезание фона выполняется
    AI_READY = "AI_READY"             # rembg завершен, создан ai_white.jpg
    EDITED = "EDITED"                 # Настроены параметры кропа/поворота
    S3_UPLOADING = "S3_UPLOADING"     # Фоновая выгрузка в Yandex S3
    S3_READY = "S3_READY"             # Успешно выгружен в облако Ozon CDN
    ARCHIVED = "ARCHIVED"             # Финализирован в Vault книги
    ERROR = "ERROR"                   # Сбой обработки или сети (доступен 1-клик retry)


class TemplateMode(str, Enum):
    """
    Режим шаблона Ozon в зависимости от года издания книги.
    - pre2011: Книги до 2011 года включительно (81 колонка)
    - post2011: Книги с 2012 года (86 колонок)
    """
    PRE2011 = "pre2011"
    POST2011 = "post2011"

