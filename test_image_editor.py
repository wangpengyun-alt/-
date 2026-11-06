# -*- coding: utf-8 -*-
"""image_editor.py 核心功能测试。运行：python -m unittest -v test_image_editor.py"""

import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import image_editor as editor


class ImageEditorCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_png(self, size=(320, 240), mode="RGB", color=(80, 120, 200), name="sample.png"):
        image = Image.new(mode, size, color)
        path = self.root / name
        image.save(path)
        return path, image

    def test_load_image_info(self):
        path, source = self.make_png()
        image, info = editor.load_image_file(path)

        self.assertEqual(image.size, (320, 240))
        self.assertEqual(info.filename, "sample.png")
        self.assertEqual(info.image_format, "PNG")
        self.assertEqual(info.width, 320)
        self.assertEqual(info.height, 240)
        self.assertEqual(info.mode, "RGB")
        self.assertIn("RGB", info.mode_label)
        self.assertRegex(info.file_size_mb, r"^\d+\.\d{2} MB$")
        self.assertEqual(
            info.file_size_mb,
            f"{os.path.getsize(path) / (1024 * 1024):.2f} MB",
        )

    def test_load_missing_file(self):
        with self.assertRaises(editor.ImageLoadError) as context:
            editor.load_image_file(self.root / "missing.png")
        self.assertIn("文件不存在", str(context.exception))

    def test_load_invalid_image(self):
        path = self.root / "not_an_image.png"
        path.write_bytes(b"this is not an image")
        with self.assertRaises(editor.ImageLoadError) as context:
            editor.load_image_file(path)
        self.assertIn("不是有效的图片", str(context.exception))

    def test_resize_only_height_keeps_ratio(self):
        image = Image.new("RGB", (400, 200))
        result = editor.resize_image(image, height=100)
        self.assertEqual(result.size, (200, 100))

    def test_resize_only_width_keeps_ratio(self):
        image = Image.new("RGB", (400, 200))
        result = editor.resize_image(image, width=100)
        self.assertEqual(result.size, (100, 50))

    def test_resize_both_dimensions(self):
        image = Image.new("RGB", (400, 200))
        result = editor.resize_image(image, width=120, height=80)
        self.assertEqual(result.size, (120, 80))

    def test_resize_rejects_invalid_arguments(self):
        image = Image.new("RGB", (400, 200))
        with self.assertRaises(editor.ValidationError):
            editor.resize_image(image)
        with self.assertRaises(editor.ValidationError):
            editor.resize_image(image, width=0)
        with self.assertRaises(editor.ValidationError):
            editor.resize_image(image, height=-10)
        with self.assertRaises(editor.ValidationError):
            editor.resize_image(image, width=editor.MAX_IMAGE_SIDE + 1)

    def test_crop_valid_region(self):
        image = Image.new("RGB", (320, 240), "white")
        result = editor.crop_image(image, 10, 20, 100, 50)
        self.assertEqual(result.size, (100, 50))

    def test_crop_out_of_bounds(self):
        image = Image.new("RGB", (320, 240))
        with self.assertRaises(editor.CropOutOfBoundsError) as context:
            editor.crop_image(image, 300, 200, 50, 50)
        message = str(context.exception)
        self.assertIn("超出图片范围", message)
        self.assertIn("320 × 240", message)

    def test_crop_rejects_negative_or_zero_size(self):
        image = Image.new("RGB", (320, 240))
        with self.assertRaises(editor.ValidationError):
            editor.crop_image(image, -1, 0, 10, 10)
        with self.assertRaises(editor.ValidationError):
            editor.crop_image(image, 0, 0, 0, 10)

    def test_rotate_all_supported_angles(self):
        image = Image.new("RGB", (400, 200))
        self.assertEqual(editor.rotate_image(image, 90).size, (200, 400))
        self.assertEqual(editor.rotate_image(image, 180).size, (400, 200))
        self.assertEqual(editor.rotate_image(image, 270).size, (200, 400))
        with self.assertRaises(editor.ValidationError):
            editor.rotate_image(image, 45)

    def test_rotate_90_is_clockwise(self):
        image = Image.new("RGB", (2, 1))
        image.putpixel((0, 0), (255, 0, 0))
        image.putpixel((1, 0), (0, 0, 255))
        rotated = editor.rotate_image(image, 90)
        self.assertEqual(rotated.size, (1, 2))
        self.assertEqual(rotated.getpixel((0, 0))[:3], (255, 0, 0))
        self.assertEqual(rotated.getpixel((0, 1))[:3], (0, 0, 255))

    def test_grayscale_rgb(self):
        image = Image.new("RGB", (20, 20), (255, 0, 0))
        result = editor.to_grayscale(image)
        self.assertEqual(result.mode, "L")
        self.assertLess(result.getpixel((0, 0)), 150)

    def test_grayscale_preserves_alpha(self):
        image = Image.new("RGBA", (20, 20), (255, 0, 0, 128))
        result = editor.to_grayscale(image)
        self.assertEqual(result.mode, "LA")
        self.assertEqual(result.getpixel((0, 0))[1], 128)

    def test_save_jpeg_from_rgba_uses_white_background(self):
        image = Image.new("RGBA", (20, 20), (255, 0, 0, 0))
        target = self.root / "transparent.jpg"
        saved = editor.save_image(image, target)
        self.assertTrue(saved.exists())
        with Image.open(saved) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertEqual(result.mode, "RGB")
            r, g, b = result.convert("RGB").getpixel((0, 0))
            self.assertGreater(r, 245)
            self.assertGreater(g, 245)
            self.assertGreater(b, 245)

    def test_save_grayscale_alpha_as_jpeg_stays_grayscale(self):
        image = Image.new("LA", (20, 20), (100, 0))
        target = self.root / "gray_alpha.jpg"
        editor.save_image(image, target)
        with Image.open(target) as result:
            self.assertEqual(result.mode, "L")
            self.assertGreater(result.getpixel((0, 0)), 245)

    def test_save_converts_png_to_jpg(self):
        source_path, _ = self.make_png()
        image, _ = editor.load_image_file(source_path)
        target = self.root / "converted.jpg"
        editor.save_image(image, target, source_path=source_path)
        with Image.open(target) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertEqual(result.size, (320, 240))

    def test_save_converts_jpg_to_png(self):
        source_path = self.root / "source.jpg"
        Image.new("RGB", (120, 80), (20, 80, 160)).save(source_path, quality=90)
        image, _ = editor.load_image_file(source_path)
        target = self.root / "converted.png"
        editor.save_image(image, target, source_path=source_path)
        with Image.open(target) as result:
            self.assertEqual(result.format, "PNG")
            self.assertEqual(result.size, (120, 80))

    def test_save_refuses_to_overwrite_source(self):
        source_path, _ = self.make_png()
        image, _ = editor.load_image_file(source_path)
        with self.assertRaises(editor.ValidationError) as context:
            editor.save_image(image, source_path, source_path=source_path)
        self.assertIn("不能保存到原文件", str(context.exception))

    def test_save_rejects_unknown_extension(self):
        image = Image.new("RGB", (10, 10))
        with self.assertRaises(editor.ValidationError):
            editor.save_image(image, self.root / "output.xyz")

    def test_save_rejects_missing_extension(self):
        image = Image.new("RGB", (10, 10))
        with self.assertRaises(editor.ValidationError):
            editor.save_image(image, self.root / "output")

    def test_document_undo_and_reset(self):
        path, _ = self.make_png()
        document = editor.ImageDocument.from_file(path)
        original_size = document.image.size
        document.apply(editor.resize_image(document.image, width=100), "缩放")
        self.assertTrue(document.can_undo)
        self.assertNotEqual(document.image.size, original_size)
        undone = document.undo()
        self.assertEqual(undone, "缩放")
        self.assertEqual(document.image.size, original_size)
        self.assertFalse(document.can_undo)

        document.apply(editor.rotate_image(document.image, 90), "旋转")
        self.assertTrue(document.is_modified)
        self.assertTrue(document.reset())
        self.assertEqual(document.image.size, original_size)

    def test_parse_helpers(self):
        self.assertEqual(editor.parse_positive_int(" 12 ", "宽度"), 12)
        self.assertIsNone(editor.parse_optional_positive_int("", "宽度"))
        self.assertEqual(editor.parse_nonnegative_int("0", "X 坐标"), 0)
        with self.assertRaises(editor.ValidationError):
            editor.parse_positive_int("abc", "宽度")
        with self.assertRaises(editor.ValidationError):
            editor.parse_nonnegative_int("-1", "X 坐标")


if __name__ == "__main__":
    unittest.main()
