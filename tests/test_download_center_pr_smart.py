import unittest

from app.view.download_center_interface import DownloadCenterInterface


class TestableDownloadCenterInterface(DownloadCenterInterface):
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

    def test_professional_video_mode_can_enable_hevc_postprocess(self):
        interface = TestableDownloadCenterInterface.__new__(TestableDownloadCenterInterface)
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
        interface = TestableDownloadCenterInterface.__new__(TestableDownloadCenterInterface)
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
