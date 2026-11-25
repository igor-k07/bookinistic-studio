"""
test_hardcore_audit.py: Хардкорный аудит-набор тестов (Adversarial QA).
Воспроизводит граничные случаи, гонки, инъекции спецсимволов и реальные баги,
выявленные при архитектурном анализе системы.
Тесты с декоратором @unittest.expectedFailure фиксируют подтвержденные баги,
ожидающие исправления.
"""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core.barcode import generate_ean13_from_article
from core.domain.enums import BookCondition, TemplateMode
from core.domain.models import Dimensions
from core.domain.rules import (
    calculate_gost_dimensions,
    format_annotation_with_warning,
    resolve_template_mode,
)
from server import state as mobile_state
from services.ai_service import extract_json_safely, sanitize_ai_book_data


class TestHardcoreDomainAndModels(unittest.TestCase):
    """Граничные тесты доменного слоя и моделей."""

    @unittest.expectedFailure
    def test_dimensions_float_string_crash(self):
        """
        БАГ: Если форма или ИИ передают дробную строку габаритов (например '130.5'),
        Dimensions.from_dict и calculate_gost_dimensions падают с ValueError при int('130.5').
        """
        dims = Dimensions.from_dict({"width": "130.5", "length": "205.0", "height": "15", "weight": "250.5"})
        self.assertEqual(dims.width_mm, 130)

        gost = calculate_gost_dimensions(
            format_code="84x108/32",
            pages=200,
            existing_dimensions={"width": "130.5"},
        )
        self.assertEqual(gost["width"], 131)

    def test_resolve_template_mode_dirty_years(self):
        """Проверка определения эпохи шаблона при грязных строках года."""
        self.assertEqual(resolve_template_mode("1985 г."), TemplateMode.PRE2011)
        self.assertEqual(resolve_template_mode("[2011]"), TemplateMode.PRE2011)
        self.assertEqual(resolve_template_mode("2012-2013"), TemplateMode.POST2011)
        self.assertEqual(resolve_template_mode("б.г."), TemplateMode.PRE2011)
        self.assertEqual(resolve_template_mode(None), TemplateMode.PRE2011)

    def test_annotation_warning_idempotency(self):
        """Повторное форматирование аннотации не должно дублировать предупреждение."""
        once = format_annotation_with_warning("Описание книги.", has_defects=True)
        twice = format_annotation_with_warning(once, has_defects=True)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count("ВНИМАНИЕ! КНИГА НЕ НОВАЯ"), 1)

    def test_barcode_dirty_article(self):
        """Генератор EAN-13 должен выдавать валидный 13-значный код даже при мусорном артикуле."""
        code = generate_ean13_from_article("DP-B-ABC-!@#")
        self.assertEqual(len(code), 13)
        self.assertTrue(code.isdigit())


class TestHardcoreMobileState(unittest.TestCase):
    """Аудит потокобезопасности и конечного автомата мобильных загрузок (server/state.py)."""

    def setUp(self):
        mobile_state._latest_mobile_event = {"event_id": 0, "timestamp": 0, "images": []}
        mobile_state._upload_sessions = {}

    @unittest.expectedFailure
    def test_reset_mobile_state_then_reload_poll_zero(self):
        """
        БАГ: reset_mobile_state() очищает images=[], но обновляет timestamp на текущий и не сбрасывает event_id.
        При перезагрузке вкладки десктопа (last_id=0) сервер отвечает has_new=True с пустым массивом images=[].
        """
        mobile_state.record_mobile_upload(1000, [{"name": "cover.jpg"}])
        mobile_state.reset_mobile_state()
        res = mobile_state.check_mobile_events(0)
        self.assertFalse(res["has_new"])

    @unittest.expectedFailure
    def test_out_of_order_chunks_lose_photos(self):
        """
        БАГ: Если последний чанк (chunk_index=1, is_last_chunk=True) приходит по сети раньше первого (chunk_index=0),
        сессия преждевременно завершается и теряет фотографии из чанка 0.
        """
        res1 = mobile_state.add_mobile_chunk("sess_1", chunk_index=1, total_chunks=2, is_last_chunk=True, images=[{"name": "2.jpg"}])
        res0 = mobile_state.add_mobile_chunk("sess_1", chunk_index=0, total_chunks=2, is_last_chunk=False, images=[{"name": "1.jpg"}])
        # Ожидаем, что сессия дождется оба чанка и вернет 2 фото
        self.assertFalse(res1["is_complete"])
        self.assertTrue(res0["is_complete"])
        self.assertEqual(res0["total_count"], 2)


class TestHardcoreDBService(unittest.TestCase):
    """Аудит SQLite-слоя (services/db_service.py)."""

    @unittest.expectedFailure
    def test_article_overflow_above_10000(self):
        """
        БАГ: В get_next_article_number() стоит жесткий фильтр `if val > 10000: continue`.
        Когда каталог перевалит за 10 000 книг, система начнет выдавать коллизии артикулов!
        """
        import services.db_service as db_service

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_db = os.path.join(tmpdir, "catalog.db")
            tmp_vault = os.path.join(tmpdir, "vault")
            os.makedirs(tmp_vault, exist_ok=True)

            with patch("config.get_db_path", return_value=tmp_db), \
                 patch("config.get_vault_dir", return_value=tmp_vault), \
                 patch("config.VAULT_DIR", tmp_vault), \
                 patch("config.get_active_store_id", return_value="test_store"):
                db_service.init_db("test_store")
                with db_service.get_db_connection("test_store") as conn:
                    conn.execute(
                        "INSERT INTO books (article, title, data) VALUES (?, ?, ?)",
                        ("DP-B-10005", "Книга 10005", "{}"),
                    )
                    conn.commit()
                    conn.close()

                next_art = db_service.get_next_article_number(verify_ozon=False, store_id="test_store")
                self.assertEqual(next_art, "DP-B-10006")


class TestHardcoreAIExtraction(unittest.TestCase):
    """Аудит парсинга и санитизации ответов Gemini Vision (services/ai_service.py)."""

    def test_extract_json_with_fences_and_control_chars(self):
        """Извлечение JSON при наличии markdown-блоков, лишнего текста и управляющих символов."""
        raw = 'Вот результат анализа:\n```json\n{"title": "Война и \x07мир", "year": 1980}\n```\nУдачи!'
        parsed = extract_json_safely(raw)
        self.assertEqual(parsed["year"], 1980)
        self.assertIn("Война и", parsed["title"])

    def test_extract_json_invalid_raises(self):
        """При полностью сломанном ответе ИИ должно выбрасываться исключение, а не возвращаться {}."""
        with self.assertRaises(Exception):
            extract_json_safely("Извините, я не могу распознать это изображение.")

    def test_sanitize_ai_strips_isbn_pre2011_when_not_on_photo(self):
        """Для советских и до-2011 книг галлюцинированный ISBN должен удаляться, если не подтвержден на фото."""
        data = {"title": "Физика", "year": "1975", "isbn": "978-5-12345-678-9", "isbn_found_on_photo": False}
        clean = sanitize_ai_book_data(data)
        self.assertEqual(clean["isbn"], "")


if __name__ == "__main__":
    unittest.main()

