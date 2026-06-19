import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QApplication, QWidget

from app.view.download_center_interface import CurrentPageStackedWidget, DownloadCenterInterface


class _SizedPage(QWidget):
    def __init__(self, size):
        super().__init__()
        self._size = size

    def sizeHint(self):
        return self._size

    def minimumSizeHint(self):
        return self._size


class CurrentPageStackedWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_size_hints_follow_current_page(self):
        stack = CurrentPageStackedWidget()
        compact_page = _SizedPage(QSize(300, 80))
        detailed_page = _SizedPage(QSize(300, 420))
        stack.addWidget(compact_page)
        stack.addWidget(detailed_page)

        stack.setCurrentWidget(compact_page)
        self.assertEqual(stack.sizeHint().height(), 80)
        self.assertEqual(stack.minimumSizeHint().height(), 80)

        stack.setCurrentWidget(detailed_page)
        self.assertEqual(stack.sizeHint().height(), 420)
        self.assertEqual(stack.minimumSizeHint().height(), 420)

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


if __name__ == "__main__":
    unittest.main()
