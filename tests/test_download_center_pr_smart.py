import unittest

from app.view.download_center_interface import DownloadCenterInterface


class TestableDownloadCenterInterface(DownloadCenterInterface):
    def tr(self, text):
        return text


class PrSmartFormatSelectionTests(unittest.TestCase):
    def _interface_with_preview(self, preview_data):
        interface = TestableDownloadCenterInterface.__new__(TestableDownloadCenterInterface)
        interface.preview_data = preview_data
        return interface

    def test_pr_smart_audio_prefers_supported_format_over_higher_bitrate_opus(self):
        interface = self._interface_with_preview(
            {
                "audio_formats": [
                    {
                        "format_id": "251",
                        "acodec": "opus",
                        "ext": "webm",
                        "abr": 160,
                        "filesize": 6_000_000,
                        "channels": 2,
                    },
                    {
                        "format_id": "140",
                        "acodec": "mp4a.40.2",
                        "ext": "m4a",
                        "abr": 129,
                        "filesize": 5_000_000,
                        "channels": 2,
                    },
                ]
            }
        )

        selected = interface._pick_pr_smart_audio_format()

        self.assertEqual(selected["format_id"], "140")

    def test_pr_smart_audio_uses_highest_spec_among_aac_or_m4a_formats(self):
        interface = self._interface_with_preview(
            {
                "audio_formats": [
                    {
                        "format_id": "140",
                        "acodec": "mp4a.40.2",
                        "ext": "m4a",
                        "abr": 129,
                        "filesize": 5_000_000,
                        "channels": 2,
                    },
                    {
                        "format_id": "m4a-256",
                        "acodec": "mp4a.40.2",
                        "ext": "m4a",
                        "abr": 256,
                        "filesize": 9_000_000,
                        "channels": 2,
                    },
                    {
                        "format_id": "mp3-320",
                        "acodec": "mp3",
                        "ext": "mp3",
                        "abr": 320,
                        "filesize": 11_000_000,
                        "channels": 2,
                    },
                ]
            }
        )

        selected = interface._pick_pr_smart_audio_format()

        self.assertEqual(selected["format_id"], "m4a-256")

    def test_pr_smart_request_pairs_video_only_stream_with_supported_audio(self):
        interface = self._interface_with_preview(
            {
                "video_formats": [
                    {
                        "format_id": "av1-opus",
                        "quality": "1080p",
                        "height": 1080,
                        "fps": 60,
                        "filesize": 120_000_000,
                        "vcodec": "av01",
                        "acodec": "opus",
                        "ext": "webm",
                        "has_audio": True,
                    },
                    {
                        "format_id": "av1-video",
                        "quality": "1080p",
                        "height": 1080,
                        "fps": 60,
                        "filesize": 115_000_000,
                        "vcodec": "av01",
                        "acodec": "none",
                        "ext": "webm",
                        "has_audio": False,
                    },
                ],
                "audio_formats": [
                    {
                        "format_id": "251",
                        "quality": "160kbps",
                        "acodec": "opus",
                        "ext": "webm",
                        "abr": 160,
                        "filesize": 6_000_000,
                        "channels": 2,
                    },
                    {
                        "format_id": "140",
                        "quality": "129kbps",
                        "acodec": "mp4a.40.2",
                        "ext": "m4a",
                        "abr": 129,
                        "filesize": 5_000_000,
                        "channels": 2,
                    },
                ],
            }
        )

        request = interface._build_pr_smart_request()

        self.assertEqual(request["selected_video_format_id"], "av1-video")
        self.assertEqual(request["selected_audio_format_id"], "140")
        self.assertEqual(request["format_selector"], "av1-video+140")

    def test_pr_smart_audio_falls_back_to_supported_audio_when_no_aac_or_m4a(self):
        interface = self._interface_with_preview(
            {
                "audio_formats": [
                    {
                        "format_id": "mp3-192",
                        "acodec": "mp3",
                        "ext": "mp3",
                        "abr": 192,
                        "filesize": 7_000_000,
                        "channels": 2,
                    },
                    {
                        "format_id": "wav",
                        "acodec": "pcm_s16le",
                        "ext": "wav",
                        "abr": 1411,
                        "filesize": 40_000_000,
                        "channels": 2,
                    },
                ]
            }
        )

        selected = interface._pick_pr_smart_audio_format()

        self.assertEqual(selected["format_id"], "wav")

    def test_pr_smart_audio_does_not_select_unsupported_audio_only_formats(self):
        interface = self._interface_with_preview(
            {
                "audio_formats": [
                    {
                        "format_id": "251",
                        "acodec": "opus",
                        "ext": "webm",
                        "abr": 160,
                    },
                    {
                        "format_id": "251-vorbis",
                        "acodec": "vorbis",
                        "ext": "webm",
                        "abr": 128,
                    },
                ]
            }
        )

        self.assertIsNone(interface._pick_pr_smart_audio_format())


if __name__ == "__main__":
    unittest.main()
