import unittest

from app.view.download_center_interface import DownloadCenterInterface


class DownloadCenterInterfaceHarness(DownloadCenterInterface):
    def tr(self, text):
        return text


class _CheckBox:
    def __init__(self, checked=False):
        self._checked = checked

    def isChecked(self):
        return self._checked


class _Combo:
    def __init__(self, data, text=""):
        self._data = data
        self._text = text

    def currentData(self):
        return self._data

    def currentText(self):
        return self._text


class PrSmartFormatSelectionTests(unittest.TestCase):
    def _interface_with_preview(self, preview_data):
        interface = DownloadCenterInterfaceHarness.__new__(DownloadCenterInterfaceHarness)
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
        self.assertTrue(request["ensure_mp4_output"])

    def test_pr_smart_prefers_same_height_mp4_avc_over_vp9(self):
        interface = self._interface_with_preview(
            {
                "video_formats": [
                    {
                        "format_id": "vp9-1080",
                        "quality": "1080p",
                        "height": 1080,
                        "fps": 60,
                        "filesize": 240_000_000,
                        "vcodec": "vp9",
                        "acodec": "none",
                        "ext": "webm",
                        "has_audio": False,
                    },
                    {
                        "format_id": "avc-1080",
                        "quality": "1080p",
                        "height": 1080,
                        "fps": 60,
                        "filesize": 180_000_000,
                        "vcodec": "avc1.64002a",
                        "acodec": "none",
                        "ext": "mp4",
                        "has_audio": False,
                    },
                ],
                "audio_formats": [
                    {
                        "format_id": "140",
                        "quality": "129kbps",
                        "acodec": "mp4a.40.2",
                        "ext": "m4a",
                        "abr": 129,
                    }
                ],
            }
        )

        request = interface._build_pr_smart_request()

        self.assertEqual(request["selected_video_format_id"], "avc-1080")
        self.assertEqual(request["selected_audio_format_id"], "140")
        self.assertEqual(request["format_selector"], "avc-1080+140")

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

    def test_time_range_automatic_presets_prefer_same_height_mp4_avc(self):
        interface = self._interface_with_preview(
            {
                "video_formats": [
                    {
                        "format_id": "vp9-1080",
                        "quality": "1080p",
                        "height": 1080,
                        "fps": 60,
                        "filesize": 200_000_000,
                        "vcodec": "vp9",
                        "acodec": "none",
                        "ext": "webm",
                        "has_audio": False,
                    },
                    {
                        "format_id": "avc-1080",
                        "quality": "1080p",
                        "height": 1080,
                        "fps": 60,
                        "filesize": 180_000_000,
                        "vcodec": "avc1.64002a",
                        "acodec": "none",
                        "ext": "mp4",
                        "has_audio": False,
                    },
                ],
                "audio_formats": [
                    {
                        "format_id": "140",
                        "acodec": "mp4a.40.2",
                        "ext": "m4a",
                        "abr": 129,
                    }
                ],
            }
        )

        for preset in ("best_quality", "mp4_compatible", "pr_smart"):
            with self.subTest(preset=preset):
                request = {"format_selector": "vp9-1080+140"}
                interface._apply_automatic_time_range_format(request, preset)
                self.assertEqual(request["selected_video_format_id"], "avc-1080")
                self.assertEqual(request["selected_audio_format_id"], "140")
                self.assertEqual(request["format_selector"], "avc-1080+140")
                self.assertIn("同分辨率", request["time_range_format_notice"])

    def test_time_range_format_does_not_drop_resolution_for_avc(self):
        interface = self._interface_with_preview(
            {
                "video_formats": [
                    {
                        "format_id": "vp9-1080",
                        "height": 1080,
                        "fps": 60,
                        "vcodec": "vp9",
                        "acodec": "none",
                        "ext": "webm",
                        "has_audio": False,
                    },
                    {
                        "format_id": "avc-720",
                        "height": 720,
                        "fps": 60,
                        "vcodec": "avc1.64001f",
                        "acodec": "none",
                        "ext": "mp4",
                        "has_audio": False,
                    },
                ],
                "audio_formats": [
                    {"format_id": "140", "acodec": "mp4a.40.2", "ext": "m4a"}
                ],
            }
        )
        request = {"format_selector": "vp9-1080+140"}

        interface._apply_automatic_time_range_format(request, "pr_smart")

        self.assertEqual(request["format_selector"], "vp9-1080+140")
        self.assertNotIn("selected_video_format_id", request)
        self.assertIn("保留原格式", request["time_range_format_notice"])

    def test_time_range_format_does_not_override_custom_preset(self):
        interface = self._interface_with_preview({"video_formats": [], "audio_formats": []})
        request = {"format_selector": "custom-selector"}

        interface._apply_automatic_time_range_format(request, "custom_preferences")

        self.assertEqual(request, {"format_selector": "custom-selector"})

    def test_professional_video_mode_can_enable_hevc_postprocess(self):
        interface = DownloadCenterInterfaceHarness.__new__(DownloadCenterInterfaceHarness)
        interface.current_mode_key = "professional"
        interface.professional_mode_combo = _Combo("video")
        interface.selected_video_format = {"format_id": "401", "has_audio": False}
        interface.selected_audio_format = None
        interface.professional_postprocess_checkbox = _CheckBox(True)
        interface.subtitle_checkbox = _CheckBox(False)
        interface.thumbnail_checkbox = _CheckBox(False)
        interface.metadata_checkbox = _CheckBox(False)
        interface.description_txt_checkbox = _CheckBox(False)
        interface.enable_time_ranges_checkbox = _CheckBox(False)

        request = interface._build_download_request()

        self.assertTrue(request["need_video"])
        self.assertEqual(request["download_mode"], "video")
        self.assertEqual(request["format_selector"], "401")
        self.assertTrue(request["pr_smart_transcode_hevc_on_av1"])

    def test_professional_audio_mode_does_not_enable_hevc_postprocess(self):
        interface = DownloadCenterInterfaceHarness.__new__(DownloadCenterInterfaceHarness)
        interface.current_mode_key = "professional"
        interface.professional_mode_combo = _Combo("audio")
        interface.selected_video_format = None
        interface.selected_audio_format = {"format_id": "140"}
        interface.professional_postprocess_checkbox = _CheckBox(True)
        interface.subtitle_checkbox = _CheckBox(False)
        interface.thumbnail_checkbox = _CheckBox(False)
        interface.metadata_checkbox = _CheckBox(False)
        interface.description_txt_checkbox = _CheckBox(False)
        interface.enable_time_ranges_checkbox = _CheckBox(False)

        request = interface._build_download_request()

        self.assertTrue(request["need_video"])
        self.assertEqual(request["download_mode"], "audio")
        self.assertEqual(request["format_selector"], "140")
        self.assertFalse(request["pr_smart_transcode_hevc_on_av1"])


if __name__ == "__main__":
    unittest.main()
