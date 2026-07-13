import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from app.view.subtitle_interface import SubtitleInterface
from app.view.transcription_interface import TranscriptionInterface


class WorkspaceUxStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_transcription_handoff_waits_for_generated_subtitles(self):
        interface = TranscriptionInterface()

        self.assertFalse(interface.send_to_translate_action.isEnabled())
        self.assertIn("请先完成转录", interface.send_to_translate_action.toolTip())

        model_combo = (
            interface.transcription_setting_card.mlx_whisper_widget.model_card.comboBox
        )
        self.assertEqual(model_combo.cursorPosition(), 0)
        self.assertEqual(model_combo.toolTip(), model_combo.text())
        interface.deleteLater()

    def test_subtitle_actions_follow_the_loaded_file_state(self):
        interface = SubtitleInterface()

        self.assertFalse(interface.start_button.isEnabled())
        self.assertFalse(interface.save_button.isEnabled())
        self.assertIn("先打开或拖入", interface.log_text.placeholderText())

        fixture = Path(__file__).parent / "fixtures" / "transcript.srt"
        interface.load_subtitle_file(str(fixture))

        self.assertTrue(interface.start_button.isEnabled())
        self.assertTrue(interface.save_button.isEnabled())
        interface.deleteLater()


if __name__ == "__main__":
    unittest.main()
