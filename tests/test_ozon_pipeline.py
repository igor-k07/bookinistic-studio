"""
test_ozon_pipeline.py: Модульные тесты прямого пайплайна Ozon API и Smart Update.
Запуск: python3 -m unittest tests/test_ozon_pipeline.py
"""

import unittest
from unittest.mock import MagicMock, patch

from core.use_cases.save_book import SaveBookUseCase
from services.ozon_service import (
    _build_ozon_book_attributes,
    check_product_exists,
    get_import_task_info,
    publish_product_to_ozon,
    smart_publish_or_update,
    update_ozon_product_attributes,
    update_ozon_product_prices,
)


class TestOzonPipeline(unittest.TestCase):
    def test_build_ozon_book_attributes(self):
        book = {
            "title": "Собачье сердце",
            "author": "Михаил Булгаков",
            "publisher": "Советский писатель",
            "year": 1987,
            "pages": 240,
            "isbn": "978-5-0000-0000-0",
            "cover_type": "Твердый переплет",
            "genre": "Проза",
        }
        attrs = _build_ozon_book_attributes(book)
        self.assertIsInstance(attrs, list)

        attr_map = {a["id"]: a["values"][0]["value"] for a in attrs}
        self.assertEqual(attr_map.get(4180), "Собачье сердце")
        self.assertEqual(attr_map.get(105), "Михаил Булгаков")
        self.assertEqual(attr_map.get(85), "Советский писатель")
        self.assertEqual(attr_map.get(4081), "1987")
        self.assertEqual(attr_map.get(4051), "240")
        self.assertEqual(attr_map.get(4184), "978-5-0000-0000-0")
        self.assertEqual(attr_map.get(9356), "Твердый переплет")
        self.assertEqual(attr_map.get(23273), "Проза")

    @patch("services.ozon_service.check_ozon_connection")
    def test_smart_publish_or_update_unconfigured(self, mock_conn):
        mock_conn.return_value = {"connected": False}
        res = smart_publish_or_update({"article": "DP-B-99999", "title": "Книга"})
        self.assertFalse(res["success"])
        self.assertTrue(res.get("skipped"))
        self.assertIn("не настроен", res.get("error", ""))

    @patch("services.ozon_service.check_ozon_connection")
    @patch("services.ozon_service.check_product_exists")
    @patch("services.ozon_service.publish_product_to_ozon")
    def test_smart_publish_new_product(self, mock_publish, mock_exists, mock_conn):
        mock_conn.return_value = {"connected": True}
        mock_exists.return_value = (False, None)
        mock_publish.return_value = (True, {"task_id": 123456})

        book = {
            "article": "DP-B-03500",
            "title": "Герой нашего времени",
            "author": "Михаил Лермонтов",
            "price": "400",
        }
        res = smart_publish_or_update(book)
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "imported")
        self.assertEqual(res["task_id"], 123456)
        mock_publish.assert_called_once()

    @patch("services.ozon_service.check_ozon_connection")
    @patch("services.ozon_service.check_product_exists")
    @patch("services.ozon_service.update_ozon_product_attributes")
    @patch("services.ozon_service.update_ozon_product_pictures")
    @patch("services.ozon_service.update_ozon_product_prices")
    def test_smart_update_existing_product(self, mock_prices, mock_pics, mock_attrs, mock_exists, mock_conn):
        mock_conn.return_value = {"connected": True}
        mock_exists.return_value = (True, {"id": 987654321, "offer_id": "DP-B-03500"})
        mock_attrs.return_value = (True, {"task_id": 777})
        mock_pics.return_value = (True, {"task_id": 888})
        mock_prices.return_value = (True, {"result": []})

        book = {
            "article": "DP-B-03500",
            "title": "Герой нашего времени (исправлено)",
            "author": "Лермонтов М.Ю.",
            "price": "550",
            "main_photo_url": "https://cdn.example.com/cover.jpg",
        }
        res = smart_publish_or_update(book)
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "updated")
        self.assertEqual(res["product_id"], 987654321)
        mock_attrs.assert_called_once()
        mock_pics.assert_called_once()
        mock_prices.assert_called_once()

    @patch("services.ozon_service._make_ozon_request")
    def test_get_import_task_info(self, mock_req):
        mock_req.return_value = (True, {"result": {"items": [{"status": "imported"}]}})
        ok, res = get_import_task_info(12345)
        self.assertTrue(ok)
        mock_req.assert_called_with("/v1/product/import/info", {"task_id": 12345})


class TestSaveBookUseCaseOzonIntegration(unittest.TestCase):
    @patch("core.use_cases.save_book.save_book_vault_photos")
    @patch("core.use_cases.save_book.s3_upload_book_photos")
    @patch("core.use_cases.save_book.save_book_to_db")
    @patch("core.use_cases.save_book.sync_book_to_excel")
    @patch("services.ozon_service.smart_publish_or_update")
    def test_save_book_use_case_publishes_to_ozon(
        self, mock_ozon_smart, mock_sync_excel, mock_save_db, mock_s3_upload, mock_vault
    ):
        mock_vault.return_value = ("folder_DP-B-00001", ["01_cover.jpg"])
        mock_s3_upload.return_value = ("https://s3.example.com/cover.jpg", "")
        mock_sync_excel.return_value = {"success": True, "file_name": "test.xlsx", "row": 2}
        mock_ozon_smart.return_value = {
            "success": True,
            "action": "imported",
            "published": True,
            "task_id": 999111,
            "message": "Новая карточка успешно создана на Ozon",
        }

        use_case = SaveBookUseCase()
        payload = {
            "article": "DP-B-00001",
            "title": "Мцыри",
            "author": "Михаил Лермонтов",
            "price": "350",
            "slots_photos": {
                "cover_front": {"id": 1, "name": "cover.jpg"}
            }
        }
        res = use_case.execute(payload)

        self.assertTrue(res["success"])
        self.assertEqual(res["article"], "DP-B-00001")
        self.assertIsNotNone(res.get("ozon_info"))
        self.assertTrue(res["ozon_info"]["published"])
        self.assertEqual(res["ozon_info"]["task_id"], 999111)


if __name__ == "__main__":
    unittest.main()

