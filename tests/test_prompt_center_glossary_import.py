import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget

from app.core.subtitle_processor.prompt import PROMPT_TERM_GLOSSARY
from app.view.setting_interface import PromptCenterDialog


class PromptCenterGlossaryImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.parent = QWidget()
        self.parent.resize(1200, 800)
        self.dialog = PromptCenterDialog(self.parent)
        glossary_index = next(
            index
            for index, item in enumerate(self.dialog.prompt_items)
            if item["id"] == PROMPT_TERM_GLOSSARY
        )
        self.dialog.promptCombo.setCurrentIndex(glossary_index)

    def tearDown(self):
        self.dialog.deleteLater()
        self.parent.deleteLater()

    def test_import_button_is_only_visible_for_term_glossary(self):
        self.assertFalse(self.dialog.importButton.isHidden())

        self.dialog.promptCombo.setCurrentIndex(0)

        self.assertTrue(self.dialog.importButton.isHidden())

    def test_import_markdown_extracts_and_normalizes_pairs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            glossary_path = Path(temp_dir) / "glossary.md"
            glossary_path.write_text(
                "## 主角\nWise → 哲\nBelle -> 铃\n上级：[[index]]\n",
                encoding="utf-8",
            )
            with patch.object(
                self.dialog,
                "tr",
                side_effect=lambda text: text,
            ), patch(
                "app.view.setting_interface.QFileDialog.getOpenFileName",
                return_value=(str(glossary_path), ""),
            ), patch("app.view.setting_interface.InfoBar.success") as success:
                self.dialog.import_glossary_file()

        self.assertEqual(self.dialog.textEdit.toPlainText(), "Wise -> 哲\nBelle -> 铃")
        success.assert_called_once()


if __name__ == "__main__":
    unittest.main()
