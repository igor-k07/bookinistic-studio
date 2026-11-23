"""
test_asset_service.py: Тесты для ядра управления ассетами Bookinistic Photo Engine V2.
"""

import io
import os
import shutil
import tempfile
import unittest
from PIL import Image

from core.domain.enums import AssetStatus
import services.asset_service as asset_service


class TestAssetService(unittest.TestCase):
    def setUp(self):
        # Создаем временное тестовое изображение 200x200
        im = Image.new("RGB", (200, 200), color=(180, 50, 50))
        buf = io.BytesIO()
        im.save(buf, format="JPEG")
        self.sample_bytes = buf.getvalue()

    def test_create_and_get_asset(self):
        asset = asset_service.create_asset_from_bytes(
            file_bytes=self.sample_bytes,
            filename="test_cover.jpg",
            book_id=1,
            slot="cover_front",
        )
        self.assertTrue(asset.id.startswith("ast_"))
        self.assertEqual(asset.status, AssetStatus.UPLOADED)
        self.assertTrue(os.path.exists(asset.original_path))
        self.assertTrue(os.path.exists(asset.preview_path))

        fetched = asset_service.get_asset(asset.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, asset.id)
        self.assertEqual(fetched.slot, "cover_front")

        # Cleanup
        asset_service.delete_asset(asset.id)

    def test_update_transforms(self):
        asset = asset_service.create_asset_from_bytes(
            file_bytes=self.sample_bytes,
            filename="test_crop.jpg",
        )
        crop_box = {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}
        updated = asset_service.update_asset_transformations(
            asset_id=asset.id,
            crop=crop_box,
            rotation=90,
            filters={"brightness": 10, "contrast": 5},
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, AssetStatus.EDITED)
        self.assertEqual(updated.transformations.get("rotation"), 90)
        self.assertEqual(updated.transformations.get("crop"), crop_box)

        # Рендеринг финального изображения
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            ok = asset_service.render_final_image(asset.id, tmp_path)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(tmp_path))
            with Image.open(tmp_path) as out_im:
                # Оригинал 200x200 повернуть на 90 и кропнуть 0.8x0.8 -> 160x160
                self.assertEqual(out_im.size, (160, 160))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            asset_service.delete_asset(asset.id)


if __name__ == "__main__":
    unittest.main()

