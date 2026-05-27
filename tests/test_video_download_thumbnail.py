import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.thread.video_download_thread import _normalize_thumbnail_to_png


class VideoDownloadThumbnailTests(unittest.TestCase):
    def test_normalizes_downloaded_thumbnail_to_png(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            jpg_path = Path(tmpdir) / "thumbnail.jpg"
            Image.new("RGB", (4, 4), color=(255, 0, 0)).save(jpg_path, format="JPEG")

            png_path = Path(_normalize_thumbnail_to_png(jpg_path))

            self.assertEqual(png_path.suffix, ".png")
            self.assertTrue(png_path.exists())
            self.assertFalse(jpg_path.exists())
            with Image.open(png_path) as image:
                self.assertEqual(image.format, "PNG")
