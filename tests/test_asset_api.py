"""
test_asset_api.py: Тестирование REST API эндпоинтов Bookinistic Photo Engine V2.
"""

import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from server.router import RequestContext
import server.controllers.asset_controller as asset_controller
import server.controllers.book_controller as book_controller
import services.asset_service as asset_service


class MockHTTPHandler:
    def __init__(self, path: str, method: str = "GET", body: bytes = b"", headers: dict = None):
        self.path = path
        self.command = method
        self.headers = headers or {}
        self.body = body
        self.rfile = io.BytesIO(body)
        self.response_data = None
        self.response_status = None

    def send_json(self, data, status=200):
        self.response_data = data
        self.response_status = status

    def send_error_json(self, error, status=500):
        self.response_data = {"success": False, "error": str(error)}
        self.response_status = status


class TestAssetApi(unittest.TestCase):
    def setUp(self):
        # Генерируем тестовый JPEG
        im = Image.new("RGB", (100, 100), color=(120, 80, 200))
        buf = io.BytesIO()
        im.save(buf, format="JPEG")
        self.sample_bytes = buf.getvalue()

    def test_upload_assets_multipart(self):
        boundary = "----WebKitFormBoundaryTest123"
        content_type = f"multipart/form-data; boundary={boundary}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="slot"\r\n\r\ncover_front\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file_0"; filename="cover.jpg"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode("latin1") + self.sample_bytes + f"\r\n--{boundary}--\r\n".encode("latin1")

        handler = MockHTTPHandler(
            "/api/assets/upload",
            method="POST",
            body=body,
            headers={"Content-Type": content_type, "Content-Length": str(len(body))},
        )
        ctx = RequestContext(
            handler=handler,
            method="POST",
            path="/api/assets/upload",
            body=body,
        )

        res = asset_controller.upload_assets(ctx)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("count"), 1)
        asset_info = res["assets"][0]
        self.assertTrue(asset_info["id"].startswith("ast_"))
        self.assertEqual(asset_info["slot"], "cover_front")
        self.assertTrue(asset_info["preview_url"].startswith("/api/assets/"))

        # Очистка
        asset_service.delete_asset(asset_info["id"])

    def test_transform_and_assign_api(self):
        asset = asset_service.create_asset_from_bytes(self.sample_bytes, filename="test.jpg")

        # 1. Assign
        assign_body = json.dumps({
            "asset_id": asset.id,
            "slot": "illustrations",
            "book_id": 1,
            "slot_order": 2,
        }).encode("utf-8")
        handler = MockHTTPHandler("/api/assets/assign", method="POST", body=assign_body)
        ctx = RequestContext(handler=handler, method="POST", path="/api/assets/assign", body=assign_body)
        res_assign = asset_controller.assign_slot_api(ctx)
        self.assertTrue(res_assign.get("success"))
        self.assertEqual(res_assign["asset"]["slot"], "illustrations")

        # 2. Transform
        trans_body = json.dumps({
            "asset_id": asset.id,
            "crop": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8},
            "rotation": 90,
        }).encode("utf-8")
        handler = MockHTTPHandler("/api/assets/transform", method="POST", body=trans_body)
        ctx = RequestContext(handler=handler, method="POST", path="/api/assets/transform", body=trans_body)
        res_trans = asset_controller.transform_asset_api(ctx)
        self.assertTrue(res_trans.get("success"))
        self.assertEqual(res_trans["asset"]["transformations"]["rotation"], 90)

        # Очистка
        asset_service.delete_asset(asset.id)

    def test_storage_stats_api(self):
        handler = MockHTTPHandler("/api/storage/stats", method="GET")
        ctx = RequestContext(handler=handler, method="GET", path="/api/storage/stats")
        res = asset_controller.storage_stats_api(ctx)
        self.assertTrue(res.get("success"))
        self.assertIn("total_mb", res.get("stats", {}))

    @patch("services.ozon_service.update_ozon_product_pictures")
    def test_update_ozon_pictures_api(self, mock_update):
        mock_update.return_value = (True, {"result": "ok"})
        body = json.dumps({
            "article": "DP-B-99999",
            "primary_image": "https://s3.ru/img1.jpg",
            "images": ["https://s3.ru/img2.jpg"]
        }).encode("utf-8")
        handler = MockHTTPHandler("/api/ozon/update_pictures", method="POST", body=body)
        ctx = RequestContext(handler=handler, method="POST", path="/api/ozon/update_pictures", body=body)
        res = book_controller.update_ozon_pictures(ctx)
        self.assertTrue(res.get("success"))
        mock_update.assert_called_once()


if __name__ == "__main__":
    unittest.main()

