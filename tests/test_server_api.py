"""
test_server_api.py: Тестирование API контроллеров и диспетчеризации запросов.
"""

import io
import json
import unittest
from unittest.mock import patch

from server.handler import BatchHandler
from server.router import RequestContext
from server.routes import build_router


class MockHTTPHandler:
    """Мок HTTP-обработчика для вызова контроллеров."""
    def __init__(self, path: str, method: str = "GET", body=b""):
        if isinstance(body, dict):
            body_bytes = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body_bytes = body.encode("utf-8")
        else:
            body_bytes = body
        self.path = path
        self.command = method
        self.headers = {"Content-Length": str(len(body_bytes))}
        self.body = body_bytes
        self.rfile = io.BytesIO(body_bytes)
        self.status_code = None
        self.sent_headers = {}
        self.response_data = None

    def send_response(self, code):
        self.status_code = code

    def send_header(self, key, value):
        self.sent_headers[key] = value

    def end_headers(self):
        pass

    def send_json(self, data, status=200):
        self.status_code = status
        self.response_data = data

    def send_error_json(self, err, status=500):
        self.status_code = status
        self.response_data = {"success": False, "error": str(err)}


class TestServerAPI(unittest.TestCase):
    """Интеграционные тесты API роутера."""

    def setUp(self):
        self.router = build_router()
        from config import switch_ozon_profile, get_active_store_id
        self.original_store = get_active_store_id()
        switch_ozon_profile("primary")

    def tearDown(self):
        from config import switch_ozon_profile
        if self.original_store == "2727930":
            switch_ozon_profile("test")
        else:
            switch_ozon_profile("primary")

    def test_get_next_article_endpoint(self):
        handler = MockHTTPHandler("/api/get_next_article", method="GET")
        ok = self.router.dispatch(handler, "GET")
        self.assertTrue(ok)
        self.assertEqual(handler.status_code, 200)
        self.assertTrue(handler.response_data.get("success"))
        self.assertTrue(handler.response_data.get("article", "").startswith("DP-B-"))

    def test_get_memos_endpoint(self):
        handler = MockHTTPHandler("/api/get_memos", method="GET")
        ok = self.router.dispatch(handler, "GET")
        self.assertTrue(ok)
        self.assertEqual(handler.status_code, 200)
        memos = handler.response_data.get("memos", [])
        self.assertGreater(len(memos), 3)

    def test_get_references_endpoint(self):
        handler = MockHTTPHandler("/api/references", method="GET")
        ok = self.router.dispatch(handler, "GET")
        self.assertTrue(ok)
        self.assertEqual(handler.status_code, 200)
        refs = handler.response_data.get("references", {})
        self.assertIn("brands", refs)
        self.assertIn("authors", refs)

    def test_get_books_endpoint(self):
        handler = MockHTTPHandler("/api/get_books?mode=pre2011", method="GET")
        ok = self.router.dispatch(handler, "GET")
        self.assertTrue(ok)
        self.assertEqual(handler.status_code, 200)
        self.assertTrue(handler.response_data.get("success"))
        self.assertIn("books", handler.response_data)

    def test_proactive_s3_route_registered(self):
        self.assertIn("/api/s3_upload_slot_photo", self.router._post_routes)
        # Проверяем валидацию параметров при пустом теле
        handler = MockHTTPHandler("/api/s3_upload_slot_photo", method="POST", body=b"{}")
        ok = self.router.dispatch(handler, "POST")
        self.assertTrue(ok)
        self.assertEqual(handler.status_code, 500)
        self.assertFalse(handler.response_data.get("success"))

    @patch("server.controllers.session_controller.clear_session_draft_storage")
    def test_clear_session_draft_endpoint(self, mock_clear):
        handler = MockHTTPHandler("/api/clear_session_draft", method="POST", body=b"{}")
        ok = self.router.dispatch(handler, "POST")
        self.assertTrue(ok)
        self.assertEqual(handler.status_code, 200)
        self.assertTrue(handler.response_data.get("success"))
        mock_clear.assert_called_once()

    def test_reset_mobile_state(self):
        from server.state import reset_mobile_state, _latest_mobile_event
        reset_mobile_state()
        self.assertEqual(_latest_mobile_event["images"], [])
        self.assertGreater(_latest_mobile_event["event_id"], 0)

    def test_reopen_book_quoted_urls(self):
        from services.vault_service import reopen_book_from_vault, resolve_photo_bytes
        book = reopen_book_from_vault("DP-B-03084")
        if book and book.get("slots", {}).get("cover_front"):
            cf = book["slots"]["cover_front"]
            # Проверяем, что URL обложки корректно закодирован без сырых не-ASCII байтов
            self.assertTrue(cf["url"].startswith("/vault/DP-B-03084"))
            self.assertIn("%", cf["url"])  # %D0... для кириллицы
            # Проверяем, что resolve_photo_bytes находит файл на диске
            img_bytes = resolve_photo_bytes(cf)
            self.assertIsNotNone(img_bytes)
            self.assertGreater(len(img_bytes), 1000)

    def test_reopen_book_cloud_proxy_urls(self):
        from services.vault_service import reopen_book_from_vault
        # DP-B-99999 не имеет папки в vault, должен загрузиться из db с прокси-ссылками
        book = reopen_book_from_vault("DP-B-99999")
        if book and book.get("slots", {}).get("cover_front"):
            cf = book["slots"]["cover_front"]
            self.assertTrue(cf["url"].startswith("/api/image_proxy?url="))

    def test_smart_save_route_registered(self):
        self.assertIn("/api/books/smart_save", self.router._post_routes)

    def test_check_article_endpoint(self):
        # 1. Существующий артикул
        handler_exist = MockHTTPHandler("/api/check_article?article=DP-B-02483", method="GET")
        ok = self.router.dispatch(handler_exist, "GET")
        self.assertTrue(ok)
        self.assertEqual(handler_exist.status_code, 200)
        self.assertTrue(handler_exist.response_data.get("exists"))
        self.assertEqual(handler_exist.response_data.get("title"), "Схимник")

        # 2. Несуществующий свободный артикул
        handler_free = MockHTTPHandler("/api/check_article?article=DP-B-77777", method="GET")
        ok_free = self.router.dispatch(handler_free, "GET")
        self.assertTrue(ok_free)
        self.assertEqual(handler_free.status_code, 200)
        self.assertFalse(handler_free.response_data.get("exists"))
        self.assertTrue(handler_free.response_data.get("suggested_next_article", "").startswith("DP-B-"))

    def test_save_book_duplicate_prevention(self):
        # Попытка создания НОВОЙ книги с уже существующим артикулом должна быть заблокирована
        handler = MockHTTPHandler(
            "/api/save_book",
            method="POST",
            body={"article": "DP-B-02483", "title": "Дубликат", "is_edit": False}
        )
        self.router.dispatch(handler, "POST")
        self.assertFalse(handler.response_data.get("success"))
        self.assertEqual(handler.response_data.get("code"), "ARTICLE_ALREADY_EXISTS")
        self.assertIn("уже занят", handler.response_data.get("error", ""))


if __name__ == "__main__":
    unittest.main()

