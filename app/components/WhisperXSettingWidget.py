from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QVBoxLayout, QWidget
from qfluentwidgets import ComboBoxSettingCard, PushSettingCard
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import RangeSettingCard, SettingCardGroup, SingleDirectionScrollArea
from qfluentwidgets import SwitchSettingCard

from ..common.config import cfg
from ..core.entities import TranscribeLanguageEnum
from .EditComboBoxSettingCard import EditComboBoxSettingCard
from .LineEditSettingCard import LineEditSettingCard
from .SpinBoxSettingCard import DoubleSpinBoxSettingCard


class WhisperXSettingWidget(QWidget):
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
            self.tr("WhisperX 设置（需本地 Python 依赖）"), self
        )

        self.model_card = EditComboBoxSettingCard(
            cfg.whisperx_model,
            FIF.ROBOT,
            self.tr("模型"),
            self.tr("选择或输入 WhisperX 模型名称"),
            ["large-v3", "large-v3-turbo", "medium", "small", "base"],
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

        self.auto_language_card = SwitchSettingCard(
            FIF.SEARCH,
            self.tr("Auto Detect Language"),
            self.tr("Detect language automatically with WhisperX"),
            cfg.whisperx_auto_language,
            self.setting_group,
        )

        self.device_card = ComboBoxSettingCard(
            cfg.whisperx_device,
            FIF.IOT,
            self.tr("运行设备"),
            self.tr("WhisperX 运行设备"),
            ["cuda", "cpu"],
            self.setting_group,
        )

        self.compute_type_card = EditComboBoxSettingCard(
            cfg.whisperx_compute_type,
            FIF.ROBOT,
            self.tr("Compute Type"),
            self.tr("设置 WhisperX 的计算精度"),
            ["float16", "int8", "int8_float16", "float32"],
            self.setting_group,
        )

        self.batch_size_card = RangeSettingCard(
            cfg.whisperx_batch_size,
            FIF.SPEED_HIGH,
            self.tr("Batch Size"),
            self.tr("WhisperX 转录批大小"),
            parent=self.setting_group,
        )

        self.hotwords_card = LineEditSettingCard(
            cfg.whisperx_hotwords,
            FIF.CHAT,
            self.tr("Hotwords"),
            self.tr("Optional hotwords for WhisperX transcription"),
            "",
            self.setting_group,
        )

        self.initial_prompt_card = LineEditSettingCard(
            cfg.whisperx_initial_prompt,
            FIF.DOCUMENT,
            self.tr("Initial Prompt"),
            self.tr("Optional context prompt for WhisperX transcription"),
            "",
            self.setting_group,
        )

        self.vad_method_card = ComboBoxSettingCard(
            cfg.whisperx_vad_method,
            FIF.MUSIC,
            self.tr("VAD Method"),
            self.tr("Voice activity detection backend"),
            ["silero", "pyannote"],
            self.setting_group,
        )

        self.vad_threshold_card = DoubleSpinBoxSettingCard(
            cfg.whisperx_vad_threshold,
            FIF.VOLUME,
            self.tr("VAD Threshold"),
            self.tr("Voice activity detection onset threshold"),
            minimum=0.0,
            maximum=1.0,
            decimals=2,
            step=0.05,
            parent=self.setting_group,
        )

        local_silero_dir = cfg.get(cfg.whisperx_local_silero_dir) or self.tr("未设置")
        self.local_silero_dir_card = PushSettingCard(
            self.tr("选择"),
            FIF.FOLDER,
            self.tr("Local Silero Repo"),
            local_silero_dir,
            self.setting_group,
        )

        self.word_timestamps_card = SwitchSettingCard(
            FIF.UNIT,
            self.tr("词级时间轴"),
            self.tr("开启后生成词级时间戳，单句会更短，便于后续断句"),
            cfg.whisperx_word_timestamps,
            self.setting_group,
        )

        self.align_card = SwitchSettingCard(
            FIF.ALIGNMENT,
            self.tr("对齐校正"),
            self.tr("启用 WhisperX 对齐以获得更稳定的时间戳"),
            cfg.whisperx_align,
            self.setting_group,
        )

        self.diarize_card = SwitchSettingCard(
            FIF.PEOPLE,
            self.tr("Speaker Diarization"),
            self.tr("Detect different speakers with WhisperX"),
            cfg.whisperx_diarize,
            self.setting_group,
        )

        local_diarize_dir = cfg.get(cfg.whisperx_local_diarize_dir) or self.tr("未设置")
        self.local_diarize_dir_card = PushSettingCard(
            self.tr("选择"),
            FIF.FOLDER,
            self.tr("Local Diarization Model"),
            local_diarize_dir,
            self.setting_group,
        )

        self.hf_token_card = LineEditSettingCard(
            cfg.whisperx_hf_token,
            FIF.FINGERPRINT,
            self.tr("HF Token"),
            self.tr("可选，用于需要 HuggingFace 权限的对齐模型"),
            "hf_",
            self.setting_group,
        )

        self.language_card.comboBox.setMaxVisibleItems(6)
        self.model_card.comboBox.setMinimumWidth(200)
        self.language_card.comboBox.setMinimumWidth(200)
        self.device_card.comboBox.setMinimumWidth(200)
        self.compute_type_card.comboBox.setMinimumWidth(200)
        self.hotwords_card.lineEdit.setMinimumWidth(200)
        self.initial_prompt_card.lineEdit.setMinimumWidth(200)
        self.vad_method_card.comboBox.setMinimumWidth(200)
        self.hf_token_card.lineEdit.setMinimumWidth(200)

        self.setting_group.addSettingCard(self.model_card)
        self.setting_group.addSettingCard(self.language_card)
        self.setting_group.addSettingCard(self.auto_language_card)
        self.setting_group.addSettingCard(self.device_card)
        self.setting_group.addSettingCard(self.compute_type_card)
        self.setting_group.addSettingCard(self.batch_size_card)
        self.setting_group.addSettingCard(self.hotwords_card)
        self.setting_group.addSettingCard(self.initial_prompt_card)
        self.setting_group.addSettingCard(self.vad_method_card)
        self.setting_group.addSettingCard(self.vad_threshold_card)
        self.setting_group.addSettingCard(self.local_silero_dir_card)
        self.setting_group.addSettingCard(self.word_timestamps_card)
        self.setting_group.addSettingCard(self.align_card)
        self.setting_group.addSettingCard(self.diarize_card)
        self.setting_group.addSettingCard(self.local_diarize_dir_card)
        self.setting_group.addSettingCard(self.hf_token_card)

        self.containerLayout.addWidget(self.setting_group)
        self.containerLayout.addStretch(1)

        self.scrollArea.setWidget(self.container)
        self.scrollArea.setWidgetResizable(True)

        self.main_layout.addWidget(self.scrollArea)

        self.local_silero_dir_card.clicked.connect(self.__on_local_silero_dir_clicked)
        self.local_diarize_dir_card.clicked.connect(self.__on_local_diarize_dir_clicked)
        self.vad_method_card.comboBox.currentTextChanged.connect(
            self.__update_local_silero_dir_card_state
        )
        self.diarize_card.checkedChanged.connect(self.__update_local_diarize_dir_card_state)
        self.__update_local_silero_dir_card_state(
            self.vad_method_card.comboBox.currentText()
        )
        self.__update_local_diarize_dir_card_state(self.diarize_card.isChecked())

    def __on_local_silero_dir_clicked(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择 Silero 仓库文件夹"),
            cfg.get(cfg.whisperx_local_silero_dir) or "./",
        )
        if not folder:
            return

        cfg.set(cfg.whisperx_local_silero_dir, folder)
        self.local_silero_dir_card.setContent(folder)

    def __on_local_diarize_dir_clicked(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择本地说话人分离模型文件夹"),
            cfg.get(cfg.whisperx_local_diarize_dir) or "./",
        )
        if not folder:
            return

        cfg.set(cfg.whisperx_local_diarize_dir, folder)
        self.local_diarize_dir_card.setContent(folder)

    def __update_local_silero_dir_card_state(self, vad_method: str):
        enabled = (vad_method or "") == "silero"
        self.local_silero_dir_card.setEnabled(enabled)

    def __update_local_diarize_dir_card_state(self, enabled: bool):
        self.local_diarize_dir_card.setEnabled(bool(enabled))
