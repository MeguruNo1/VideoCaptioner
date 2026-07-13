import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QBoxLayout
from qfluentwidgets import CheckBox

from app.view.download_center_interface import DownloadCenterInterface


class DownloadCenterLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_mode_panel_hides_inactive_page_instead_of_reserving_its_height(self):
        interface = DownloadCenterInterface()
        interface.resize(1120, 680)
        interface.show()
        self.app.processEvents()

        with patch.object(interface, "_save_download_preferences"):
            interface._switch_download_mode("simple")
            self.app.processEvents()
            self.assertFalse(interface.simple_panel.isHidden())
            self.assertTrue(interface.professional_panel.isHidden())
            self.assertLess(interface.mode_panel_container.height(), 220)

            interface._switch_download_mode("professional")
            self.app.processEvents()
            self.assertTrue(interface.simple_panel.isHidden())
            self.assertFalse(interface.professional_panel.isHidden())
        interface.deleteLater()

    def test_compact_layout_stacks_preview_and_wraps_download_options(self):
        interface = DownloadCenterInterface()
        interface.resize(700, 760)
        interface.show()
        interface._set_preview_visible(True)
        self.app.processEvents()

        self.assertEqual(
            interface.preview_card_layout.direction(), QBoxLayout.TopToBottom
        )
        compact_positions = [
            interface.download_options_grid.getItemPosition(
                interface.download_options_grid.indexOf(checkbox)
            )[:2]
            for checkbox in interface.download_option_checkboxes
        ]
        self.assertEqual(compact_positions, [(0, 0), (0, 1), (1, 0), (1, 1)])
        self.assertEqual(interface.output_dir_layout.direction(), QBoxLayout.TopToBottom)
        compact_custom_positions = [
            (
                interface.custom_preferences_grid.getItemPosition(
                    interface.custom_preferences_grid.indexOf(label)
                )[:2],
                interface.custom_preferences_grid.getItemPosition(
                    interface.custom_preferences_grid.indexOf(combo)
                )[:2],
            )
            for label, combo in interface.custom_preference_fields
        ]
        self.assertEqual(
            compact_custom_positions,
            [((0, 0), (0, 1)), ((1, 0), (1, 1)), ((2, 0), (2, 1))],
        )

        interface.resize(1000, 760)
        self.app.processEvents()
        self.assertEqual(
            interface.preview_card_layout.direction(), QBoxLayout.LeftToRight
        )
        wide_positions = [
            interface.download_options_grid.getItemPosition(
                interface.download_options_grid.indexOf(checkbox)
            )[:2]
            for checkbox in interface.download_option_checkboxes
        ]
        self.assertEqual(wide_positions, [(0, 0), (0, 1), (0, 2), (0, 3)])
        self.assertEqual(interface.output_dir_layout.direction(), QBoxLayout.LeftToRight)
        wide_custom_positions = [
            (
                interface.custom_preferences_grid.getItemPosition(
                    interface.custom_preferences_grid.indexOf(label)
                )[:2],
                interface.custom_preferences_grid.getItemPosition(
                    interface.custom_preferences_grid.indexOf(combo)
                )[:2],
            )
            for label, combo in interface.custom_preference_fields
        ]
        self.assertEqual(
            wide_custom_positions,
            [((0, 0), (0, 1)), ((0, 2), (0, 3)), ((0, 4), (0, 5))],
        )
        interface.deleteLater()

    def test_download_options_use_fluent_checkboxes_with_larger_hit_targets(self):
        interface = DownloadCenterInterface()

        self.assertEqual(len(interface.download_checkboxes), 9)
        for checkbox in interface.download_checkboxes:
            self.assertIsInstance(checkbox, CheckBox)
            self.assertGreaterEqual(checkbox.minimumHeight(), 28)
        interface.deleteLater()

    def test_preview_summarizes_large_subtitle_language_lists(self):
        interface = DownloadCenterInterface()
        preview = {
            "title": "Example",
            "uploader": "Uploader",
            "duration_text": "01:00",
            "manual_subtitle_languages": [],
            "auto_subtitle_languages": [f"lang-{index}" for index in range(20)],
        }

        interface._render_preview_card(preview)

        self.assertIn("自动 20 种", interface.preview_subtitle_label.text())
        self.assertIn("lang-4…", interface.preview_subtitle_label.text())
        self.assertNotIn("lang-19", interface.preview_subtitle_label.text())
        self.assertIn("lang-19", interface.preview_subtitle_label.toolTip())
        interface.deleteLater()

    def test_time_range_progress_switches_between_indeterminate_and_determinate(self):
        interface = DownloadCenterInterface()

        interface._render_download_detail_panel(
            {
                "phase": "locating",
                "indeterminate": True,
                "percent": "",
                "elapsed": "00:07",
                "section_index": 1,
                "section_count": 2,
                "status": "正在定位片段起点",
            }
        )
        self.assertIs(interface.progress_stack.currentWidget(), interface.indeterminate_progress_bar)
        self.assertEqual(interface.status_label.text(), "正在定位片段起点")
        self.assertNotIn("进度：0", interface.download_detail_panel.text())

        interface._render_download_detail_panel(
            {
                "phase": "processing",
                "indeterminate": False,
                "percent": "42.5",
                "speed": "1.3x",
                "eta": "01:10",
                "elapsed": "00:12",
                "section_index": 1,
                "section_count": 2,
                "status": "正在下载并生成片段",
            }
        )
        self.assertIs(interface.progress_stack.currentWidget(), interface.progress_bar)
        self.assertEqual(interface.progress_bar.value(), 42)
        self.assertIn("进度：42.5%", interface.download_detail_panel.text())
        interface.deleteLater()

    def test_restores_preview_and_interrupted_download_progress(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "download_center_state.json"
            with patch.object(DownloadCenterInterface, "DOWNLOAD_STATE_PATH", state_path):
                interface = DownloadCenterInterface()
                interface.parsed_url = "https://example.test/video"
                interface.preview_data = {
                    "url": interface.parsed_url,
                    "title": "Resume me",
                    "uploader": "Tester",
                    "duration_text": "01:00",
                    "upload_date": "",
                    "view_count_text": "",
                    "thumbnail_bytes": b"thumbnail",
                    "video_formats": [],
                    "audio_formats": [],
                    "manual_subtitle_languages": [],
                    "auto_subtitle_languages": [],
                    "has_manual_subtitles": False,
                    "has_auto_subtitles": False,
                    "info_dict": {"duration": 60},
                }
                interface._pending_subtitle_mode = "auto"
                interface._pending_work_dir = temp_dir
                interface._save_download_state(
                    status="interrupted",
                    request={"need_video": True},
                    progress=37,
                    detail={"percent": "37", "status": "网络中断"},
                )
                interface.deleteLater()

                restored = DownloadCenterInterface()
                self.assertEqual(restored.parsed_url, "https://example.test/video")
                self.assertEqual(restored.preview_data["title"], "Resume me")
                self.assertEqual(restored.progress_bar.value(), 37)
                self.assertEqual(restored._pending_download_request, {"need_video": True})
                self.assertEqual(restored.start_button.text(), "继续下载")
                self.assertIn("恢复上次下载进度", restored.status_label.text())
                restored.deleteLater()

    def test_automatic_subtitles_prefer_english_and_allow_language_change(self):
        interface = DownloadCenterInterface()
        interface.preview_data = {
            "manual_subtitle_languages": [],
            "auto_subtitle_languages": ["ru", "en", "ja"],
        }
        mode_blocked = interface.subtitle_mode_combo.blockSignals(True)
        interface._set_combo_current_data(interface.subtitle_mode_combo, "auto", "auto")
        interface.subtitle_mode_combo.blockSignals(mode_blocked)
        language_blocked = interface.subtitle_language_combo.blockSignals(True)
        interface._set_combo_current_data(interface.subtitle_language_combo, "en", "en")
        interface.subtitle_language_combo.blockSignals(language_blocked)
        from app.common.config import cfg

        original_get = cfg.get
        with patch.object(
            cfg,
            "get",
            side_effect=lambda item: (
                "en" if item is cfg.download_center_subtitle_language else original_get(item)
            ),
        ):
            interface._populate_subtitle_languages()

        self.assertEqual(interface.subtitle_language_combo.currentData(), "en")
        blocked = interface.subtitle_language_combo.blockSignals(True)
        interface._set_combo_current_data(interface.subtitle_language_combo, "ru", "en")
        interface.subtitle_language_combo.blockSignals(blocked)
        self.assertEqual(interface.subtitle_language_combo.currentData(), "ru")
        interface.deleteLater()


if __name__ == "__main__":
    unittest.main()
