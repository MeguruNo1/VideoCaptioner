from PyQt5.QtWidgets import (
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from app.core.entities import TranscribeModelEnum
from .MLXWhisperSettingWidget import MLXWhisperSettingWidget
from .WhisperXSettingWidget import WhisperXSettingWidget


class TranscriptionSettingCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 设置界面堆叠
        self.stacked_widget = QStackedWidget(self)

        # 添加各个设置界面
        self.whisperx_widget = WhisperXSettingWidget(self)
        self.mlx_whisper_widget = MLXWhisperSettingWidget(self)

        self.stacked_widget.addWidget(self.whisperx_widget)
        self.stacked_widget.addWidget(self.mlx_whisper_widget)

        self.main_layout.addWidget(self.stacked_widget)

    def on_model_changed(self, _value):
        if _value == TranscribeModelEnum.MLX_WHISPER.value:
            self.stacked_widget.setCurrentWidget(self.mlx_whisper_widget)
            return
        self.stacked_widget.setCurrentWidget(self.whisperx_widget)
