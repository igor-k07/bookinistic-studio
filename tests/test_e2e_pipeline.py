"""
test_e2e_pipeline.py: Сквозное E2E тестирование жизненного цикла книги и работы с Ozon API.
Включает:
1. Сквозной цикл сохранения книги (SaveBookUseCase -> DB, Vault, S3, Ozon API, Excel fallback).
2. Мульти-профильное переключение магазинов Ozon (Основной <-> Тестовый) на уровне бэкенда и API.
3. Опрос статусов асинхронных задач Ozon (Task Polling endpoint).
4. Проверка реального подключения к боевому тестовому магазину Ozon (Client-Id 2727930).
"""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

import config
from core.use_cases.save_book import SaveBookUseCase
from server.routes import build_router
import services.ozon_service as ozon_service


class MockHTTPHandler:
    """Мок HTTP-обработчика для тестирования контроллеров через Router."""
    def __init__(self, path: str, method: str = "GET", body=None):
        if body is None:
            body_bytes = b""
        elif isinstance(body, dict):
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


class TestE2EBookLifecycle(unittest.TestCase):
    """Сквозное тестирование сохранения книги через SaveBookUseCase."""

    @patch("services.tunnel_service.start_tunnel", return_value="https://tunnel.mock")
    @patch("services.tunnel_service.get_tunnel_url", return_value="https://tunnel.mock")
    @patch("core.use_cases.save_book.save_book_vault_photos")
    @patch("core.use_cases.save_book.s3_upload_book_photos")
    @patch("core.use_cases.save_book.save_book_to_db")
    @patch("core.use_cases.save_book.sync_book_to_excel")
    @patch("services.ozon_service.smart_publish_or_update")
    def test_full_save_lifecycle_ozon_success(
        self, mock_ozon_smart, mock_sync_excel, mock_save_db, mock_s3_upload, mock_vault, mock_tunnel_get, mock_tunnel_start
    ):
        mock_vault.return_value = ("folder_DP-B-05001", ["01_cover.jpg", "02_spine.jpg"])
        mock_s3_upload.return_value = ("https://cdn.example.com/cover.jpg", "https://cdn.example.com/all.jpg")
        mock_sync_excel.return_value = {"success": True, "file_name": "backup.xlsx", "row": 15}
        mock_ozon_smart.return_value = {
            "success": True,
            "action": "imported",
            "published": True,
            "task_id": 888777,
            "message": "Новая карточка успешно создана на Ozon",
        }

        book_payload = {
            "article": "DP-B-05001",
            "title": "Мастер и Маргарита",
            "author": "Михаил Булгаков",
            "publisher": "Художественная литература",
            "year": 1980,
            "pages": 448,
            "price": "1200",
            "old_price": "1680",
            "weight": 550,
            "cover_type": "Твердый переплет",
            "condition": "Отличная",
            "description": "Классический роман в твердом переплете.",
            "slots_photos": {
                "cover_front": {"id": 1, "name": "cover.jpg"},
                "spine": {"id": 2, "name": "spine.jpg"},
            },
        }

        use_case = SaveBookUseCase()
        result = use_case.execute(book_payload)

        self.assertTrue(result["success"])
        self.assertEqual(result["article"], "DP-B-05001")
        self.assertIsNotNone(result.get("ozon_info"))
        self.assertTrue(result["ozon_info"]["published"])
        self.assertEqual(result["ozon_info"]["task_id"], 888777)
        self.assertEqual(result["ozon_info"]["action"], "imported")

        # Проверяем вызовы компонентов
        mock_vault.assert_called_once()
        mock_s3_upload.assert_called_once()
        self.assertEqual(mock_save_db.call_count, 2)  # Первичное сохранение + обновление status='imported'
        mock_ozon_smart.assert_called_once()

    @patch("services.tunnel_service.start_tunnel", return_value="https://tunnel.mock")
    @patch("services.tunnel_service.get_tunnel_url", return_value="https://tunnel.mock")
    @patch("core.use_cases.save_book.save_book_vault_photos")
    @patch("core.use_cases.save_book.s3_upload_book_photos")
    @patch("core.use_cases.save_book.save_book_to_db")
    @patch("core.use_cases.save_book.sync_book_to_excel")
    @patch("services.ozon_service.smart_publish_or_update")
    def test_save_lifecycle_ozon_failure_resilient_excel_fallback(
        self, mock_ozon_smart, mock_sync_excel, mock_save_db, mock_s3_upload, mock_vault, mock_tunnel_get, mock_tunnel_start
    ):
        """Если Ozon вернул ошибку, книга сохраняется локально и гарантированно экспортируется в Excel."""
        mock_vault.return_value = ("folder_DP-B-05002", ["01_cover.jpg"])
        mock_s3_upload.return_value = ("", "")
        mock_sync_excel.return_value = {"success": True, "file_name": "offline_backup.xlsx", "row": 16}
        mock_ozon_smart.return_value = {
            "success": False,
            "action": "failed",
            "published": False,
            "error": "Ozon API Timeout (504 Gateway Timeout)",
        }

        book_payload = {
            "article": "DP-B-05002",
            "title": "Евгений Онегин",
            "author": "Александр Пушкин",
            "price": "600",
            "slots_photos": {},
        }

        use_case = SaveBookUseCase()
        result = use_case.execute(book_payload)

        self.assertTrue(result["success"])
        self.assertEqual(result["article"], "DP-B-05002")
        self.assertIsNotNone(result.get("ozon_info"))
        self.assertFalse(result["ozon_info"]["published"])
        self.assertIn("Timeout", result["ozon_info"]["error"])
        mock_sync_excel.assert_called_once()


class TestE2EMultiStoreProfiles(unittest.TestCase):
    """Тестирование переключения между профилями Основного и Тестового магазинов Ozon."""

    def setUp(self):
        self.router = build_router()

    def tearDown(self):
        # Гарантируем, что после тестов активным остается тестовый магазин
        config.switch_ozon_profile("test")

    def test_store_profiles_switching_python_api(self):
        profiles_info = config.get_ozon_profiles()
        self.assertIn("profiles", profiles_info)
        self.assertTrue(len(profiles_info["profiles"]) >= 2)

        # Переключаемся на основной
        switched_to_primary = config.switch_ozon_profile("primary")
        self.assertTrue(switched_to_primary)
        cfg_primary = config.get_ozon_config()
        self.assertEqual(cfg_primary["client_id"], "870997")

        prof_state1 = config.get_ozon_profiles()
        primary_item = next(p for p in prof_state1["profiles"] if p["key"] == "primary")
        self.assertTrue(primary_item["is_active"])

        # Переключаемся на тестовый
        switched_to_test = config.switch_ozon_profile("test")
        self.assertTrue(switched_to_test)
        cfg_test = config.get_ozon_config()
        self.assertEqual(cfg_test["client_id"], "2727930")

        prof_state2 = config.get_ozon_profiles()
        test_item = next(p for p in prof_state2["profiles"] if p["key"] == "test")
        self.assertTrue(test_item["is_active"])

    def test_store_profiles_switching_http_endpoint(self):
        # Тест POST /api/ozon/switch_profile -> primary
        h_primary = MockHTTPHandler("/api/ozon/switch_profile", method="POST", body={"profile": "primary"})
        ok = self.router.dispatch(h_primary, "POST")
        self.assertTrue(ok)
        self.assertEqual(h_primary.status_code, 200)
        self.assertTrue(h_primary.response_data["success"])
        self.assertEqual(h_primary.response_data["active_profile"], "primary")

        # Проверяем через GET /api/ozon/status
        h_status1 = MockHTTPHandler("/api/ozon/status", method="GET")
        ok_stat1 = self.router.dispatch(h_status1, "GET")
        self.assertTrue(ok_stat1)
        self.assertEqual(h_status1.response_data.get("raw_client_id"), "870997")
        self.assertEqual(h_status1.response_data.get("active_profile"), "primary")

        # Тест POST /api/ozon/switch_profile -> test
        h_test = MockHTTPHandler("/api/ozon/switch_profile", method="POST", body={"profile": "test"})
        ok_test = self.router.dispatch(h_test, "POST")
        self.assertTrue(ok_test)
        self.assertEqual(h_test.status_code, 200)
        self.assertTrue(h_test.response_data["success"])
        self.assertEqual(h_test.response_data["active_profile"], "test")

        # Проверяем возврат к test
        h_status2 = MockHTTPHandler("/api/ozon/status", method="GET")
        ok_stat2 = self.router.dispatch(h_status2, "GET")
        self.assertTrue(ok_stat2)
        self.assertEqual(h_status2.response_data.get("raw_client_id"), "2727930")
        self.assertEqual(h_status2.response_data.get("active_profile"), "test")


class TestE2EOzonTaskStatusEndpoint(unittest.TestCase):
    """Тестирование контроллера опроса асинхронных задач Ozon."""

    @patch("services.ozon_service.get_import_task_info")
    def test_task_status_endpoint(self, mock_get_task_info):
        mock_get_task_info.return_value = (
            True,
            {"items": [{"status": "imported", "offer_id": "DP-B-05001"}]},
        )

        router = build_router()
        handler = MockHTTPHandler("/api/ozon/task_status?task_id=999888", method="GET")
        ok = router.dispatch(handler, "GET")
        self.assertTrue(ok)
        self.assertEqual(handler.status_code, 200)
        self.assertTrue(handler.response_data["success"])
        self.assertIn("items", handler.response_data["result"])
        self.assertEqual(handler.response_data["result"]["items"][0]["status"], "imported")


class TestE2ELiveTestStoreConnection(unittest.TestCase):
    """Проверка реального подключения к боевому тестовому магазину Ozon."""

    def test_live_connection_to_test_store(self):
        # Убеждаемся что активен тестовый магазин
        config.switch_ozon_profile("test")
        conn = ozon_service.check_ozon_connection()
        self.assertTrue(
            conn.get("connected"),
            f"Тестовый магазин (2727930) должен успешно отвечать Ozon API: {conn}",
        )
        self.assertIn("total_products", conn)


if __name__ == "__main__":
    unittest.main()
