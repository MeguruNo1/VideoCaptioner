import unittest

from app.thread.video_download_thread import _build_format_entry, normalize_preview_data


class VideoDownloadFormatLabelTests(unittest.TestCase):
    def test_ultrawide_format_shows_real_resolution_before_quality_tier(self):
        entry = _build_format_entry(
            {
                "format_id": "400",
                "ext": "mp4",
                "width": 2560,
                "height": 1072,
                "fps": 60,
                "vcodec": "av01.0.12M.08",
                "acodec": "none",
            }
        )

        self.assertEqual(entry["quality"], "2560x1072 · 1440p档 · 60FPS")
        self.assertIn("AV01", entry["details"])

    def test_landscape_format_shows_real_resolution(self):
        entry = _build_format_entry(
            {
                "format_id": "299",
                "ext": "mp4",
                "width": 1920,
                "height": 804,
                "fps": 60,
                "vcodec": "avc1.4d402a",
                "acodec": "none",
            }
        )

        self.assertEqual(entry["quality"], "1920x804 · 1080p档 · 60FPS")

    def test_vertical_format_uses_long_edge_for_quality_tier(self):
        entry = _build_format_entry(
            {
                "format_id": "short",
                "ext": "mp4",
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "vcodec": "avc1.640028",
                "acodec": "none",
            }
        )

        self.assertEqual(entry["quality"], "1080x1920 · 1080p档 · 30FPS")

    def test_preview_sort_prefers_ultrawide_1440p_tier_over_1080p_height(self):
        preview = normalize_preview_data(
            "https://example.test/video",
            {
                "formats": [
                    {
                        "format_id": "1080",
                        "ext": "mp4",
                        "width": 1920,
                        "height": 1080,
                        "fps": 60,
                        "vcodec": "avc1.64002a",
                        "acodec": "none",
                    },
                    {
                        "format_id": "400",
                        "ext": "mp4",
                        "width": 2560,
                        "height": 1072,
                        "fps": 60,
                        "vcodec": "av01.0.12M.08",
                        "acodec": "none",
                    },
                ]
            },
        )

        self.assertEqual(preview["video_formats"][0]["format_id"], "400")


if __name__ == "__main__":
    unittest.main()
