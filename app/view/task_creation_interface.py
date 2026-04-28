# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from PyQt5.QtCore import QStandardPaths, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    HyperlinkButton,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ProgressBar,
    ToolButton,
)

from app.common.config import cfg
from app.components.DonateDialog import DonateDialog
from app.components.LanguageSettingDialog import LanguageSettingDialog
from app.config import ASSETS_PATH, VERSION
from app.core.entities import (
    LLMServiceEnum,
    SupportedAudioFormats,
    SupportedVideoFormats,
    TranscribeModelEnum,
)
from app.view.log_window import LogWindow

LOGO_PATH = ASSETS_PATH / "logo.png"


class TaskCreationInterface(QWidget):
    finished = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task = None
        self.log_window = None
        self.setObjectName("TaskCreationInterface")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self.setup_ui()
        self.setup_values()
        self.setup_signals()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setObjectName("main_layout")
        self.main_layout.setSpacing(50)
        self.main_layout.addSpacing(120)
        self.setup_logo()
        self.setup_search_layout()
        self.setup_status_layout()
        self.setup_info_label()

    def setup_logo(self):
        self.logo_label = QLabel(self)
        self.logo_pixmap = QPixmap(str(LOGO_PATH)).scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.logo_label.setPixmap(self.logo_pixmap)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.logo_label)
        self.main_layout.addSpacing(10)

    def setup_search_layout(self):
        self.search_layout = QHBoxLayout()
        self.search_layout.setContentsMargins(80, 0, 80, 0)
        self.search_input = LineEdit(self)
        self.search_input.setPlaceholderText(self.tr("请拖拽文件、选择文件，或输入本地音视频路径"))
        self.search_input.setFixedHeight(40)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.focusOutEvent = lambda event: super(LineEdit, self.search_input).focusOutEvent(event)
        self.search_input.paintEvent = lambda event: super(LineEdit, self.search_input).paintEvent(event)
        self.search_input.setStyleSheet(
            self.search_input.styleSheet()
            + """
            QLineEdit {
                border-radius: 18px;
                padding: 0 20px;
                background-color: transparent;
                border: 1px solid rgba(255,255,255,0.08);
            }
            QLineEdit:focus[transparent=true] {
                border: 1px solid rgba(47,141,99,0.48);
            }
            """
        )
        self.start_button = ToolButton(FluentIcon.FOLDER, self)
        self.start_button.setFixedSize(40, 40)
        self.start_button.setStyleSheet(
            self.start_button.styleSheet()
            + """
            QToolButton {
                border-radius: 20px;
                background-color: #2F8D63;
            }
            QToolButton:hover {
                background-color: #2E805C;
            }
            QToolButton:pressed {
                background-color: #2E905C;
            }
            """
        )
        self.search_layout.addWidget(self.search_input)
        self.search_layout.addWidget(self.start_button)
        self.search_layout.setSpacing(10)
        self.main_layout.addLayout(self.search_layout)
        self.main_layout.addSpacing(100)

    def setup_status_layout(self):
        self.status_layout = QVBoxLayout()
        self.status_layout.setContentsMargins(50, 0, 30, 5)
        self.status_layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
        self.status_label = BodyLabel(self.tr("准备就绪"), self)
        self.status_label.setStyleSheet("font-size: 14px; color: #888888;")
        self.status_layout.addWidget(self.status_label, 0, Qt.AlignCenter)
        self.progress_bar = ProgressBar(self)
        self.status_label.hide()
        self.progress_bar.hide()
        self.progress_bar.setFixedWidth(300)
        self.status_layout.addWidget(self.progress_bar, 0, Qt.AlignCenter)
        self.main_layout.addStretch(1)
        self.main_layout.addLayout(self.status_layout)

    def setup_info_label(self):
        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.log_button = HyperlinkButton(url="", text=self.tr("查看日志"), parent=self)
        self.log_button.setStyleSheet(self.log_button.styleSheet() + "QPushButton { font-size: 12px; color: #2F8D63; text-decoration: underline; }")
        self.donate_button = HyperlinkButton(url="", text=self.tr("捐助"), parent=self)
        self.donate_button.setStyleSheet(self.donate_button.styleSheet() + "QPushButton { font-size: 12px; color: #2F8D63; text-decoration: underline; }")
        self.info_label = BodyLabel(self.tr(f"VideoCaptioner {VERSION} · By Weifeng"), self)
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("font-size: 12px; color: #888888;")
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.info_label)
        bottom_layout.addWidget(self.log_button)
        bottom_layout.addWidget(self.donate_button)
        bottom_layout.addStretch()
        self.main_layout.addStretch()
        self.main_layout.addWidget(bottom_container)

    def setup_signals(self):
        self.start_button.clicked.connect(self.on_start_clicked)
        self.search_input.textChanged.connect(self.on_search_input_changed)
        self.log_button.clicked.connect(self.show_log_window)
        self.donate_button.clicked.connect(self.show_donate_dialog)

    def setup_values(self):
        self.search_input.setText("")
        if cfg.llm_service.value == LLMServiceEnum.PUBLIC:
            InfoBar.warning(
                self.tr("警告"),
                self.tr("为确保字幕修正的准确性，建议到设置中配置自己的 API。"),
                duration=6000,
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,
            )

    def on_start_clicked(self):
        if self.start_button._icon == FluentIcon.FOLDER:
            desktop_path = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
            video_formats = " ".join(f"*.{fmt.value}" for fmt in SupportedVideoFormats)
            audio_formats = " ".join(f"*.{fmt.value}" for fmt in SupportedAudioFormats)
            filter_str = f"{self.tr('媒体文件')} ({video_formats} {audio_formats});;{self.tr('视频文件')} ({video_formats});;{self.tr('音频文件')} ({audio_formats})"
            file_path, _ = QFileDialog.getOpenFileName(self, self.tr("选择媒体文件"), desktop_path, filter_str)
            if file_path:
                self.search_input.setText(file_path)
            return
        self.process()

    def on_search_input_changed(self):
        self.start_button.setIcon(FluentIcon.PLAY if self.search_input.text() else FluentIcon.FOLDER)

    def dragEnterEvent(self, event):
        event.accept() if event.mimeData().hasUrls() else event.ignore()

    def dropEvent(self, event):
        files = [item.toLocalFile() for item in event.mimeData().urls()]
        supported_formats = {fmt.value for fmt in SupportedVideoFormats} | {fmt.value for fmt in SupportedAudioFormats}
        for file_path in files:
            if not os.path.isfile(file_path):
                continue
            file_ext = os.path.splitext(file_path)[1][1:].lower()
            if file_ext in supported_formats:
                self.search_input.setText(file_path)
                self.status_label.setText(self.tr("导入成功"))
                InfoBar.success(self.tr("导入成功"), self.tr("导入媒体文件成功。"), duration=1500, parent=self)
                return
            InfoBar.error(self.tr("格式错误"), self.tr("不支持该文件格式。"), duration=3000, parent=self)

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        try:
            result = urlparse(url)
            return result.scheme in ("http", "https") and bool(result.netloc)
        except ValueError:
            return False

    def _process_file(self, file_path):
        self.finished.emit(file_path)

    def set_task(self, task):
        self.task = task
        self.update_info()

    def update_info(self):
        if self.task:
            self.search_input.setText(self.task.file_path)

    def process(self):
        search_input = self.search_input.text().strip()
        if self._is_valid_url(search_input):
            InfoBar.info(
                self.tr("请前往下载中心"),
                self.tr("URL 下载已统一到“下载中心”，请先解析并下载，再送去转录。"),
                duration=4000,
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,
            )
            return

        need_language_settings = cfg.transcribe_model.value in [
            TranscribeModelEnum.WHISPER_CPP,
            TranscribeModelEnum.WHISPER_API,
            TranscribeModelEnum.FASTER_WHISPER,
            TranscribeModelEnum.WHISPER_X,
        ]
        if need_language_settings and not self.show_language_settings():
            return

        if os.path.isfile(search_input):
            self._process_file(search_input)
            return

        InfoBar.error(self.tr("错误"), self.tr("请输入本地音视频文件路径。"), duration=3000, parent=self)

    def show_language_settings(self):
        dialog = LanguageSettingDialog(self.window())
        return bool(dialog.exec_())

    def show_log_window(self):
        if self.log_window is None:
            self.log_window = LogWindow()
        if self.log_window.isHidden():
            self.log_window.show()
        else:
            self.log_window.activateWindow()

    def show_donate_dialog(self):
        DonateDialog(self).exec_()


if __name__ == "__main__":
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    window = TaskCreationInterface()
    window.show()
    sys.exit(app.exec_())
