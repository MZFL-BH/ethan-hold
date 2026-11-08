#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_slice_image.py — 测试手机长截图自适应滑窗切片器
"""

import unittest
from pathlib import Path
from PIL import Image

from scripts.slice_image import slice_long_image


class TestSliceImage(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(__file__).resolve().parent / "fixtures" / "temp_slices"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_normal_aspect_ratio_no_slice(self):
        # 100x150, ratio = 1.5 <= 2.0 -> no slice
        img_path = self.test_dir / "normal.jpg"
        img = Image.new("RGB", (100, 150), color="white")
        img.save(img_path)

        res = slice_long_image(str(img_path), str(self.test_dir))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0], str(img_path.resolve()))

    def test_long_aspect_ratio_slices_generated(self):
        # 100x800, ratio = 8.0 > 2.0 -> should slice into multiple chunks
        img_path = self.test_dir / "long.jpg"
        img = Image.new("RGB", (100, 800), color="blue")
        img.save(img_path)

        res = slice_long_image(str(img_path), str(self.test_dir))
        self.assertGreater(len(res), 2)
        for p in res:
            self.assertTrue(Path(p).exists())
            with Image.open(p) as chunk:
                # Check that height is reasonable
                self.assertLess(chunk.height, 800)


if __name__ == "__main__":
    unittest.main()
