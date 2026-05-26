from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    ComboBoxSettingCard,
    InfoBar,
    MessageBoxBase,
    PushSettingCard,
    SettingCardGroup,
    SingleDirectionScrollArea,
    SwitchSettingCard,
    TextEdit,
)
from qfluentwidgets import FluentIcon as FIF

from ..common.config import cfg
from ..core.entities import TranscribeLanguageEnum
from ..core.utils.transcript_terms import parse_hotwords_text
from .EditComboBoxSettingCard import EditComboBoxSettingCard
from .LineEditSettingCard import LineEditSettingCard


class MLXHotwordsDialog(MessageBoxBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("MLX Whisper 热词提示"))
        self.widget.setMinimumWidth(760)
        self.widget.setMaximumWidth(980)

        self.titleLabel = BodyLabel(self.tr("MLX Whisper 热词提示"), self)
        self.descLabel = BodyLabel(
            self.tr("热词会与初始提示词合并后传给 MLX Whisper 的 initial_prompt。"),
            self,
        )
        self.descLabel.setWordWrap(True)
        self.hotwordsEdit = TextEdit(self)
        self.hotwordsEdit.setMinimumSize(680, 420)
        self.hotwordsEdit.setPlainText(cfg.mlx_hotwords.value)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.descLabel)
        self.viewLayout.addWidget(self.hotwordsEdit)

        self.yesButton.setText(self.tr("保存"))
        self.cancelButton.setText(self.tr("关闭"))

    def validate(self) -> bool:
        cfg.set(cfg.mlx_hotwords, self.hotwordsEdit.toPlainText().strip())
        InfoBar.success(
            self.tr("已保存"),
            self.tr("MLX Whisper 热词提示已更新"),
            duration=2500,
            parent=self,
        )
        return True


class MLXWhisperSettingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)

        self.scrollArea = SingleDirectionScrollArea(orient=Qt.Vertical, parent=self)
        self.scrollArea.setStyleSheet(
            "QScrollArea{background: transparent; border: none}"
        )

        self.container = QWidget(self)
        self.container.setStyleSheet("QWidget{background: transparent}")
        self.containerLayout = QVBoxLayout(self.container)

        self.setting_group = SettingCardGroup(
            self.tr("MLX Whisper 设置（Apple Silicon GPU）"),
            self,
        )

        self.model_card = EditComboBoxSettingCard(
            cfg.mlx_model,
            FIF.ROBOT,
            self.tr("模型"),
            self.tr("选择或输入 MLX Whisper 模型名称或本地模型目录"),
            [
                "mlx-community/whisper-large-v3-turbo",
                "mlx-community/whisper-large-v3-mlx",
                "mlx-community/distil-whisper-large-v3",
                "mlx-community/whisper-medium",
                "mlx-community/whisper-small",
                "mlx-community/whisper-base",
                "mlx-community/whisper-tiny",
            ],
            self.setting_group,
        )

        self.language_card = ComboBoxSettingCard(
            cfg.transcribe_language,
            FIF.LANGUAGE,
            self.tr("源语言"),
            self.tr("音频的源语言"),
            [lang.value for lang in TranscribeLanguageEnum],
            self.setting_group,
        )

        self.word_timestamps_card = SwitchSettingCard(
            FIF.UNIT,
            self.tr("词级时间轴"),
            self.tr("开启后使用 MLX Whisper 原生词级时间戳"),
            cfg.mlx_word_timestamps,
            self.setting_group,
        )

        self.hotwords_card = PushSettingCard(
            self.tr("管理"),
            FIF.CHAT,
            self.tr("热词提示"),
            self._hotwords_summary(),
            self.setting_group,
        )

        self.initial_prompt_card = LineEditSettingCard(
            cfg.mlx_initial_prompt,
            FIF.DOCUMENT,
            self.tr("初始提示词"),
            self.tr("给 MLX Whisper 的可选上下文，例如语言、场景、专有名词和标点风格"),
            "",
            self.setting_group,
        )

        self.model_card.comboBox.setMinimumWidth(280)
        self.language_card.comboBox.setMinimumWidth(200)
        self.initial_prompt_card.lineEdit.setMinimumWidth(200)

        self.setting_group.addSettingCard(self.model_card)
        self.setting_group.addSettingCard(self.language_card)
        self.setting_group.addSettingCard(self.word_timestamps_card)
        self.setting_group.addSettingCard(self.hotwords_card)
        self.setting_group.addSettingCard(self.initial_prompt_card)

        self.containerLayout.addWidget(self.setting_group)
        self.containerLayout.addStretch(1)

        self.scrollArea.setWidget(self.container)
        self.scrollArea.setWidgetResizable(True)
        self.main_layout.addWidget(self.scrollArea)

        self.hotwords_card.clicked.connect(self.__on_hotwords_clicked)

    def _hotwords_summary(self) -> str:
        hotwords = parse_hotwords_text(cfg.mlx_hotwords.value)
        if not hotwords:
            return self.tr("未设置")
        preview = ", ".join(hotwords[:3])
        if len(hotwords) > 3:
            preview += self.tr(" 等 {0} 条").format(len(hotwords))
        return preview

    def __on_hotwords_clicked(self):
        dialog = MLXHotwordsDialog(self.window())
        dialog.exec_()
        self.hotwords_card.setContent(self._hotwords_summary())
