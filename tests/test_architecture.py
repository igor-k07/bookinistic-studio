"""
test_architecture.py: Набор модульных тестов чистой архитектуры Bookinistic Studio.
Проверяет доменные модели, чистые правила, роутер и сценарии использования (Use Cases).
"""

import unittest

from core.domain.enums import BookCondition, PhotoRole, TemplateMode
from core.domain.models import Book, Dimensions, PhotoItem
from core.domain.rules import (
    calculate_book_condition,
    calculate_gost_dimensions,
    format_annotation_with_warning,
    resolve_template_mode,
)
from server.router import RequestContext, Router
from server.routes import build_router


class TestDomainRules(unittest.TestCase):
    """Тестирование чистых доменных правил и формул."""

    def test_condition_without_defects(self):
        """Без фото дефектов сохранность ВСЕГДА 'Очень хорошая'."""
        cond = calculate_book_condition(has_defects=False)
        self.assertEqual(cond, BookCondition.VERY_GOOD)

    def test_condition_with_defects(self):
        """При наличии дефектов сохранность автоматически 'Хорошая'."""
        cond = calculate_book_condition(has_defects=True)
        self.assertEqual(cond, BookCondition.GOOD)

    def test_condition_manual_satisfactory(self):
        """'Удовлетворительная' сохраняется, если задана букинистом вручную."""
        cond = calculate_book_condition(has_defects=True, manual_condition="Удовлетворительная")
        self.assertEqual(cond, BookCondition.SATISFACTORY)

    def test_annotation_warning_formatting(self):
        """Предупреждение о дефектах добавляется только при наличии дефектов и не дублируется."""
        raw_text = "Интересная советская книга."
        # Нет дефектов -> чистый текст
        clean = format_annotation_with_warning(raw_text, has_defects=False)
        self.assertEqual(clean, raw_text)

        # Есть дефекты -> текст с предупреждением
        with_warn = format_annotation_with_warning(raw_text, has_defects=True)
        self.assertTrue(with_warn.startswith("ВНИМАНИЕ! КНИГА НЕ НОВАЯ"))
        self.assertIn(raw_text, with_warn)

        # Повторный вызов не должен удваивать предупреждение
        double_warn = format_annotation_with_warning(with_warn, has_defects=True)
        self.assertEqual(with_warn.count("ВНИМАНИЕ! КНИГА НЕ НОВАЯ"), 1)

    def test_gost_dimensions_independence_principle(self):
        """Принцип независимости: ручные размеры пользователя НЕ затираются."""
        existing = {
            "width_mm": 155,
            "length_mm": 225,
            "height_mm": 30,
            "weight_g": 600,
        }
        res = calculate_gost_dimensions(
            format_code="84x108/32",
            pages=320,
            cover_type="Твердый переплет",
            existing_dimensions=existing,
            allow_overwrite_manual=False,
        )
        self.assertEqual(res["width_mm"], 155)
        self.assertEqual(res["length_mm"], 225)
        self.assertEqual(res["height_mm"], 30)
        self.assertEqual(res["weight_g"], 600)

    def test_template_mode_resolution(self):
        """Книги до 2011 -> pre2011, после 2011 -> post2011."""
        self.assertEqual(resolve_template_mode(1984), TemplateMode.PRE2011)
        self.assertEqual(resolve_template_mode(2011), TemplateMode.PRE2011)
        self.assertEqual(resolve_template_mode(2015), TemplateMode.POST2011)
        self.assertEqual(resolve_template_mode(2024), TemplateMode.POST2011)


class TestPhotoRolesSpecification(unittest.TestCase):
    """Тестирование регламента работы с фото (п. 3.2 и п. 4.1 спецификации)."""

    def test_rembg_forbidden_for_titles_and_defects(self):
        """Удаление фона запрещено для титулов, текста, дефектов и иллюстраций."""
        self.assertFalse(PhotoRole.TITLE_PAGE.should_remove_background)
        self.assertFalse(PhotoRole.COLOPHON.should_remove_background)
        self.assertFalse(PhotoRole.DEFECT.should_remove_background)
        self.assertFalse(PhotoRole.ILLUSTRATION.should_remove_background)

    def test_rembg_allowed_for_covers(self):
        """Удаление фона разрешено только для обложки и задника."""
        self.assertTrue(PhotoRole.COVER_FRONT.should_remove_background)
        self.assertTrue(PhotoRole.COVER_BACK.should_remove_background)

    def test_gemini_vision_candidate_filtering(self):
        """В Gemini отправляются только обложки, титулы и мантра. Иллюстрации и дефекты не отправляются."""
        self.assertTrue(PhotoRole.COVER_FRONT.is_ai_vision_candidate)
        self.assertTrue(PhotoRole.COVER_BACK.is_ai_vision_candidate)
        self.assertTrue(PhotoRole.TITLE_PAGE.is_ai_vision_candidate)
        self.assertTrue(PhotoRole.COLOPHON.is_ai_vision_candidate)

        self.assertFalse(PhotoRole.DEFECT.is_ai_vision_candidate)
        self.assertFalse(PhotoRole.ILLUSTRATION.is_ai_vision_candidate)


class TestDomainModels(unittest.TestCase):
    """Тестирование типизированных сущностей."""

    def test_book_from_dict_and_to_dict(self):
        raw = {
            "article": "DP-B-02882",
            "title": "Хоббит",
            "author": "Толкин Джон Рональд Руэл",
            "year": "1991 г.",
            "pages": 256,
            "price": "1 500 руб.",
            "width_mm": 140,
            "length_mm": 210,
        }
        book = Book.from_dict(raw)
        self.assertEqual(book.article, "DP-B-02882")
        self.assertEqual(book.year, 1991)
        self.assertEqual(book.pages, 256)
        self.assertEqual(book.price, 1500.0)
        self.assertEqual(book.template_mode, TemplateMode.PRE2011)

        d = book.to_dict()
        self.assertEqual(d["article"], "DP-B-02882")
        self.assertEqual(d["width_mm"], 140)


class TestCleanupTempFilesUseCase(unittest.TestCase):
    """Тестирование сборщика мусора временных файлов."""

    def test_cleanup_deletes_old_files_and_keeps_recent_and_draft_files(self):
        import tempfile
        import os
        import time
        from core.use_cases.cleanup_temp_files import CleanupTempFilesUseCase

        with tempfile.TemporaryDirectory() as tmpdir:
            photos_dir = os.path.join(tmpdir, "storage", "session_photos")
            inbox_dir = os.path.join(tmpdir, "storage", "inbox")
            os.makedirs(photos_dir)
            os.makedirs(inbox_dir)

            # Создаем старый файл (2 дня назад)
            old_file = os.path.join(photos_dir, "old_photo_preview.jpg")
            with open(old_file, "w") as f:
                f.write("old data")
            two_days_ago = time.time() - (48 * 3600)
            os.utime(old_file, (two_days_ago, two_days_ago))

            # Создаем новый файл (1 час назад)
            new_file = os.path.join(photos_dir, "recent_photo_preview.jpg")
            with open(new_file, "w") as f:
                f.write("new data")

            # Создаем старый файл, но упомянутый в черновике
            draft_protected_file = os.path.join(photos_dir, "protected_photo_preview.jpg")
            with open(draft_protected_file, "w") as f:
                f.write("draft protected data")
            os.utime(draft_protected_file, (two_days_ago, two_days_ago))

            # Создаем session_draft.json
            draft_file = os.path.join(tmpdir, "storage", "session_draft.json")
            with open(draft_file, "w") as f:
                f.write('{"photoPool": [{"preview": "/session_photos/protected_photo_preview.jpg"}]}')

            uc = CleanupTempFilesUseCase(base_dir=tmpdir)
            res = uc.execute(max_age_hours=24.0, dry_run=False)

            self.assertTrue(res["success"])
            self.assertEqual(res["deleted_count"], 1)  # Только old_photo_preview.jpg
            self.assertFalse(os.path.exists(old_file))
            self.assertTrue(os.path.exists(new_file))
            self.assertTrue(os.path.exists(draft_protected_file))


class TestOzonPublishIntegration(unittest.TestCase):
    """Тестирование подготовки выгрузки книги в Ozon."""

    def test_publish_product_validation(self):
        from services.ozon_service import publish_product_to_ozon
        ok, err = publish_product_to_ozon({})
        self.assertFalse(ok)
        self.assertIn("Не указан артикул", err)

        ok2, err2 = publish_product_to_ozon({"article": "DP-B-00001"})
        self.assertFalse(ok2)
        self.assertIn("Не указано название", err2)



class TestRouter(unittest.TestCase):
    """Тестирование декларативного роутера."""

    def test_router_dispatch(self):
        router = Router()
        called = False

        @router.get("/api/test_ping")
        def ping_handler(ctx: RequestContext):
            nonlocal called
            called = True
            return {"pong": True}

        class MockHandler:
            path = "/api/test_ping"
            headers = {}
            sent_data = None
            sent_status = None

            def send_json(self, data, status=200):
                self.sent_data = data
                self.sent_status = status

        mock = MockHandler()
        dispatched = router.dispatch(mock, "GET")
        self.assertTrue(dispatched)
        self.assertTrue(called)
        self.assertEqual(mock.sent_data, {"pong": True})
        self.assertEqual(mock.sent_status, 200)

    def test_main_router_routes_count(self):
        r = build_router()
        self.assertGreaterEqual(len(r._get_routes), 15)
        self.assertGreaterEqual(len(r._post_routes), 10)
        self.assertIn("/api/save_book", r._post_routes)
        self.assertIn("/api/ai_recognize_book", r._post_routes)
        self.assertIn("/api/ai_process_photo", r._post_routes)


if __name__ == "__main__":
    unittest.main()

