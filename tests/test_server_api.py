"""
test_server_api.py: Тестирование API контроллеров и диспетчеризации запросов.
"""

import io
import json
import unittest

from server.handler import BatchHandler
from server.router import RequestContext
from server.routes import build_router


class MockHTTPHandler:
    """Мок HTTP-обработчика для вызова контроллеров."""
    def __init__(self, path: str, method: str = "GET", body: bytes = b""):
        self.path = path
        self.command = method
        self.headers = {"Content-Length": str(len(body))}
        self.body = body
        self.rfile = io.BytesIO(body)
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


if __name__ == "__main__":
    unittest.main()

