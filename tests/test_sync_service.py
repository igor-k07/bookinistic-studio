"""
test_sync_service.py: Модульные тесты сервиса синхронизации Ozon, Yandex S3 и catalog.db.
"""

import unittest

from core.domain.rules import (
    SLOT_CARD,
    SLOT_COVER_BACK,
    SLOT_COVER_FRONT,
    SLOT_DEFECTS,
    SLOT_ILLUSTRATIONS,
    classify_filename_to_slot,
)
from services.sync_service import (
    download_bytes_resilient,
    sanitize_folder_name,
)


class TestSyncService(unittest.TestCase):
    """Тестирование алгоритмов умной синхронизации."""

    def test_sanitize_folder_name(self):
        cleaned = sanitize_folder_name("Пушкин А.С. / Капитанская дочка: повесть?")
        self.assertNotIn("/", cleaned)
        self.assertNotIn(":", cleaned)
        self.assertNotIn("?", cleaned)
        self.assertTrue(len(cleaned) <= 50)

    def test_classify_in_sync_workflow(self):
        urls = [
            "https://ir.ozone.ru/s3/cover.jpg",
            "https://storage.yandexcloud.net/bucket/DP-01/04_illustration_1.jpg",
            "https://storage.yandexcloud.net/bucket/DP-01/02_cover_back.jpg",
            "https://storage.yandexcloud.net/bucket/DP-01/05_defect_1.jpg",
            "https://storage.yandexcloud.net/bucket/DP-01/99_card.jpg",
        ]
        slots = [classify_filename_to_slot(u) for u in urls]
        self.assertEqual(slots, [
            SLOT_COVER_FRONT,
            SLOT_ILLUSTRATIONS,
            SLOT_COVER_BACK,
            SLOT_DEFECTS,
            SLOT_CARD,
        ])

    def test_download_bytes_resilient_invalid_url(self):
        # Пустые или некорректные URL должны возвращать None без исключений
        self.assertIsNone(download_bytes_resilient(""))
        self.assertIsNone(download_bytes_resilient("not_a_valid_url"))


if __name__ == "__main__":
    unittest.main()
