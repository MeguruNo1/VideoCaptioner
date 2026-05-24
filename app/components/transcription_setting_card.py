from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, CardWidget, ComboBox, ComboBoxSettingCard
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (
    HyperlinkCard,
    RangeSettingCard,
    SettingCardGroup,
    SingleDirectionScrollArea,
    SwitchSettingCard,
)

from app.components.SpinBoxSettingCard import DoubleSpinBoxSettingCard

from app.config import WHISPERX_ONLY_MODE

from ..common.config import cfg
from ..core.entities import (
    FasterWhisperModelEnum,
    TranscribeLanguageEnum,
    TranscribeModelEnum,
    VadMethodEnum,
    WhisperModelEnum,
)
from .EditComboBoxSettingCard import EditComboBoxSettingCard
from .WhisperXSettingWidget import WhisperXSettingWidget

if not WHISPERX_ONLY_MODE:
    from .FasterWhisperSettingWidget import FasterWhisperSettingWidget
    from .WhisperAPISettingWidget import WhisperAPISettingWidget
    from .WhisperCppSettingWidget import WhisperCppSettingWidget


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
        self.empty_widget = QWidget(self)  # 添加空白页面作为默认显示
        self.whisperx_widget = WhisperXSettingWidget(self)

        self.stacked_widget.addWidget(self.empty_widget)  # 添加空白页面
        if not WHISPERX_ONLY_MODE:
            self.whisper_cpp_widget = WhisperCppSettingWidget(self)
            self.whisper_api_widget = WhisperAPISettingWidget(self)
            self.faster_whisper_widget = FasterWhisperSettingWidget(self)
            self.stacked_widget.addWidget(self.whisper_cpp_widget)
            self.stacked_widget.addWidget(self.whisper_api_widget)
            self.stacked_widget.addWidget(self.faster_whisper_widget)
        self.stacked_widget.addWidget(self.whisperx_widget)

        self.main_layout.addWidget(self.stacked_widget)

    def on_model_changed(self, value):
        if WHISPERX_ONLY_MODE:
            self.stacked_widget.setCurrentWidget(self.whisperx_widget)
            return

        # 切换对应的设置界面
        if value == TranscribeModelEnum.WHISPER_CPP.value:
            self.stacked_widget.setCurrentWidget(self.whisper_cpp_widget)
        elif value == TranscribeModelEnum.WHISPER_API.value:
            self.stacked_widget.setCurrentWidget(self.whisper_api_widget)
        elif value == TranscribeModelEnum.FASTER_WHISPER.value:
            self.stacked_widget.setCurrentWidget(self.faster_whisper_widget)
        elif value == TranscribeModelEnum.WHISPER_X.value:
            self.stacked_widget.setCurrentWidget(self.whisperx_widget)
        else:
            self.stacked_widget.setCurrentWidget(self.empty_widget)
