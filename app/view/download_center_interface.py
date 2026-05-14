# -*- coding: utf-8 -*-
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QBoxLayout
from qfluentwidgets import (
    Action,
    BodyLabel,
    CardWidget,
    ComboBox,
    CommandBar,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SegmentedWidget,
    isDarkTheme,
)

from app.common.config import cfg
from app.config import APPDATA_PATH
from app.core.utils.edge_cookie_utils import export_edge_cookies
from app.core.utils.windows_notification import send_windows_notification
from app.thread.video_download_thread import VideoDownloadThread, VideoPreviewThread


class AspectRatioLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._aspect_ratio = 16 / 9

    def setPixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        if not pixmap.isNull():
            self._aspect_ratio = pixmap.width() / pixmap.height()
        self._update_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if self._pixmap.isNull():
            super().setPixmap(QPixmap())
            return
        label_size = self.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            return
        scaled = self._pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        super().setPixmap(scaled)

    def heightForWidth(self, width: int) -> int:
        return int(width / self._aspect_ratio)

    def sizeHint(self):
        return QSize(240, int(240 / self._aspect_ratio))

    def hasHeightForWidth(self):
        return True


class DownloadCenterInterface(QWidget):
    send_to_transcription = pyqtSignal(str)
    SIMPLE_PRESETS = [
        ("best_quality", "最高画质（自动组装）"),
        ("mp4_compatible", "MP4 兼容优先"),
        ("pr_smart", "PR智能预设"),
        ("custom_preferences", "自定义"),
        ("audio_only", "仅音频"),
        ("subtitle_only", "仅字幕"),
        ("thumbnail_only", "仅封面"),
    ]
    PROFESSIONAL_MODES = [
        ("video_audio", "音视频（可组装）"),
        ("video", "仅视频"),
        ("audio", "仅音频"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preview_thread = None
        self.download_thread = None
        self.preview_data = None
        self.parsed_url = ""
        self.last_result = {}
        self.last_selection_summary = "暂无"
        self.latest_download_detail = {}
        self.selected_video_format = None
        self.selected_audio_format = None
        self.video_button_group = QButtonGroup(self)
        self.audio_button_group = QButtonGroup(self)
        self.video_button_group.setExclusive(True)
        self.audio_button_group.setExclusive(True)
        self.current_mode_key = "simple"
        self.time_range_rows = []
        self.controls_enabled = True
        self.download_action_state = "idle"
        self._restoring_download_preferences = True

        self.setObjectName("DownloadCenterInterface")
        self.setWindowTitle(self.tr("下载中心"))
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setup_ui()
        self._restore_download_preferences()
        self.setup_signals()
        self._restoring_download_preferences = False
        cfg.themeMode.valueChanged.connect(lambda *_: self._apply_theme_styles())
        self._refresh_download_strategy_hint()
        self._refresh_output_dir_labels()
        self._toggle_subtitle_mode_row(self.subtitle_checkbox.isChecked())
        self._set_preview_visible(False)
        self._set_result_actions_enabled(False)
        self._reset_result_labels()
        self._reset_download_detail_panel()
        self._refresh_selection_summary()
        self._apply_theme_styles()
        self._on_professional_mode_changed()
        self._set_download_action_state("idle")

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(36, 20, 36, 20)
        self.main_layout.setSpacing(12)

        self._setup_top_bar()
        self._setup_url_card()
        self._setup_content_area()
        self._setup_result_area()
        self._setup_bottom_bar()

        self._switch_download_mode("simple")
        self.mode_switch.setMinimumHeight(36)
        self.mode_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.content_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._adjust_responsive_layout()

    def _setup_top_bar(self):
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        self.command_bar = CommandBar(self)
        self.command_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.command_bar.addAction(Action(FIF.LINK, self.tr("解析链接"), triggered=self.parse_link))
        self.command_bar.addSeparator()
        self.open_folder_action = Action(FIF.FOLDER, self.tr("打开文件夹"), triggered=self.open_result_folder)
        self.command_bar.addAction(self.open_folder_action)
        self.send_to_transcription_action = Action(FIF.SEND, self.tr("送去转录"), triggered=self.send_download_to_transcription)
        self.command_bar.addAction(self.send_to_transcription_action)
        top_layout.addWidget(self.command_bar, 1)

        self.start_button = PrimaryPushButton(self.tr("开始下载"), self, icon=FIF.DOWNLOAD)
        self.start_button.setFixedHeight(34)
        top_layout.addWidget(self.start_button)

        self.main_layout.addLayout(top_layout)

    def _setup_url_card(self):
        self.url_card = CardWidget(self)
        url_card_layout = QHBoxLayout(self.url_card)
        url_card_layout.setContentsMargins(20, 14, 20, 14)
        url_card_layout.setSpacing(12)

        url_icon_label = BodyLabel(self.url_card)
        url_icon_label.setFixedSize(20, 20)
        url_icon_label.setStyleSheet("font-size: 16px;")
        url_icon_label.setText("🔗")

        self.url_input = LineEdit(self.url_card)
        self.url_input.setPlaceholderText(self.tr("请输入视频 URL，支持 B站 / YouTube / Twitter 等平台链接"))
        self.url_input.setClearButtonEnabled(True)
        self.url_input.setMinimumHeight(36)

        self.parse_button = PushButton(self.tr("解析"), self.url_card)
        self.parse_button.setFixedWidth(80)

        url_card_layout.addWidget(url_icon_label)
        url_card_layout.addWidget(self.url_input, 1)
        url_card_layout.addWidget(self.parse_button)

        self.main_layout.addWidget(self.url_card)

    def _setup_content_area(self):
        self.content_scroll = QScrollArea(self)
        self.content_scroll.setObjectName("downloadContentScroll")
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_scroll.setMinimumHeight(220)

        self.scroll_content = QWidget(self.content_scroll)
        self.scroll_content.setObjectName("downloadScrollContent")
        self.scroll_content_layout = QVBoxLayout(self.scroll_content)
        self.scroll_content_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_content_layout.setSpacing(12)

        self._setup_preview_card()
        self._setup_config_cards()

        self.scroll_content_layout.addWidget(self.preview_card)
        self.scroll_content_layout.addWidget(self.config_card)
        self.scroll_content_layout.addStretch(1)
        self.content_scroll.setWidget(self.scroll_content)

        self.main_layout.addWidget(self.content_scroll, 1)

    def _setup_preview_card(self):
        self.preview_card = CardWidget(self.scroll_content)
        self.preview_card.setObjectName("downloadPreviewPanel")
        self.preview_card_layout = QHBoxLayout(self.preview_card)
        self.preview_card_layout.setContentsMargins(20, 16, 20, 16)
        self.preview_card_layout.setSpacing(16)

        self.thumbnail_label = AspectRatioLabel(self.preview_card)
        self.thumbnail_label.setObjectName("downloadThumbnailLabel")
        self.thumbnail_label.setMinimumWidth(100)
        self.thumbnail_label.setMaximumWidth(280)
        self.thumbnail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setText(self.tr("暂无封面"))

        preview_info_layout = QVBoxLayout()
        preview_info_layout.setContentsMargins(0, 0, 0, 0)
        preview_info_layout.setSpacing(6)
        self.preview_title_label = BodyLabel(self.tr("标题：暂无"), self.preview_card)
        self.preview_title_label.setObjectName("downloadTitleLabel")
        self.preview_title_label.setWordWrap(True)
        self.preview_uploader_label = BodyLabel(self.tr("作者：暂无"), self.preview_card)
        self.preview_uploader_label.setObjectName("downloadHintLabel")
        self.preview_uploader_label.setWordWrap(True)
        self.preview_meta_label = BodyLabel(self.tr("时长 / 日期 / 播放量：暂无"), self.preview_card)
        self.preview_meta_label.setObjectName("downloadHintLabel")
        self.preview_meta_label.setWordWrap(True)
        self.preview_subtitle_label = BodyLabel(self.tr("字幕：暂无"), self.preview_card)
        self.preview_subtitle_label.setObjectName("downloadHintLabel")
        self.preview_subtitle_label.setWordWrap(True)
        preview_info_layout.addWidget(self.preview_title_label)
        preview_info_layout.addWidget(self.preview_uploader_label)
        preview_info_layout.addWidget(self.preview_meta_label)
        preview_info_layout.addWidget(self.preview_subtitle_label)
        preview_info_layout.addStretch(1)

        self.preview_card_layout.addWidget(self.thumbnail_label, 2)
        self.preview_card_layout.addLayout(preview_info_layout, 5)

    def _setup_config_cards(self):
        self.config_card = CardWidget(self.scroll_content)
        config_outer_layout = QVBoxLayout(self.config_card)
        config_outer_layout.setContentsMargins(0, 0, 0, 0)
        config_outer_layout.setSpacing(0)

        self._setup_selection_section(config_outer_layout)
        self._setup_separator(config_outer_layout)
        self._setup_options_section(config_outer_layout)

    def _setup_selection_section(self, parent_layout):
        self.selection_section = QWidget()
        selection_layout = QVBoxLayout(self.selection_section)
        selection_layout.setContentsMargins(20, 16, 20, 8)
        selection_layout.setSpacing(12)

        self.mode_switch = SegmentedWidget(self.selection_section)
        self.mode_stack = QStackedWidget(self.selection_section)
        self.mode_switch.addItem(routeKey="simple", text=self.tr("简易模式"), onClick=lambda: self._switch_download_mode("simple"))
        self.mode_switch.addItem(routeKey="professional", text=self.tr("专业模式"), onClick=lambda: self._switch_download_mode("professional"))

        self.simple_panel = QWidget(self.selection_section)
        simple_layout = QVBoxLayout(self.simple_panel)
        simple_layout.setContentsMargins(0, 0, 0, 0)
        simple_layout.setSpacing(10)
        simple_row = QHBoxLayout()
        simple_row.setSpacing(12)
        self.simple_preset_label = BodyLabel(self.tr("下载预设"), self.simple_panel)
        self.simple_preset_label.setObjectName("downloadPrimaryLabel")
        self.simple_preset_combo = ComboBox(self.simple_panel)
        for key, text in self.SIMPLE_PRESETS:
            self.simple_preset_combo.addItem(text, userData=key)
        self.simple_preset_combo.setMinimumWidth(200)
        simple_row.addWidget(self.simple_preset_label)
        simple_row.addWidget(self.simple_preset_combo)
        simple_row.addStretch(1)
        self.simple_hint_label = BodyLabel(self.tr("简易模式会自动使用稳定的 yt-dlp 格式策略，不需要手动挑选 format_id。"), self.simple_panel)
        self.simple_hint_label.setObjectName("downloadHintLabel")
        self.simple_hint_label.setWordWrap(True)

        self.custom_preferences_section = QWidget(self.simple_panel)
        custom_preferences_layout = QVBoxLayout(self.custom_preferences_section)
        custom_preferences_layout.setContentsMargins(0, 0, 0, 0)
        custom_preferences_layout.setSpacing(10)

        custom_preferences_title = BodyLabel(self.tr("自定义偏好"), self.custom_preferences_section)
        custom_preferences_title.setObjectName("downloadPrimaryLabel")

        self.custom_video_codec_label = BodyLabel(self.tr("视频编码偏好"), self.custom_preferences_section)
        self.custom_video_codec_label.setObjectName("downloadPrimaryLabel")
        self.custom_video_codec_combo = ComboBox(self.custom_preferences_section)
        self.custom_video_codec_combo.addItem(self.tr("自动"), userData="auto")
        self.custom_video_codec_combo.addItem("AVC1", userData="avc1")
        self.custom_video_codec_combo.addItem("AV1", userData="av01")
        self.custom_video_codec_combo.addItem("VP9", userData="vp9")
        self.custom_video_codec_combo.setMinimumWidth(160)

        self.custom_container_label = BodyLabel(self.tr("容器偏好"), self.custom_preferences_section)
        self.custom_container_label.setObjectName("downloadPrimaryLabel")
        self.custom_container_combo = ComboBox(self.custom_preferences_section)
        self.custom_container_combo.addItem(self.tr("自动"), userData="auto")
        self.custom_container_combo.addItem("MP4", userData="mp4")
        self.custom_container_combo.addItem("WebM", userData="webm")
        self.custom_container_combo.setMinimumWidth(160)

        self.custom_audio_codec_label = BodyLabel(self.tr("音频偏好"), self.custom_preferences_section)
        self.custom_audio_codec_label.setObjectName("downloadPrimaryLabel")
        self.custom_audio_codec_combo = ComboBox(self.custom_preferences_section)
        self.custom_audio_codec_combo.addItem(self.tr("自动"), userData="auto")
        self.custom_audio_codec_combo.addItem("MP4A", userData="mp4a")
        self.custom_audio_codec_combo.addItem("Opus", userData="opus")
        self.custom_audio_codec_combo.setMinimumWidth(160)

        custom_preferences_row = QHBoxLayout()
        custom_preferences_row.setSpacing(12)
        custom_preferences_row.addWidget(self.custom_video_codec_label)
        custom_preferences_row.addWidget(self.custom_video_codec_combo)
        custom_preferences_row.addWidget(self.custom_container_label)
        custom_preferences_row.addWidget(self.custom_container_combo)
        custom_preferences_row.addWidget(self.custom_audio_codec_label)
        custom_preferences_row.addWidget(self.custom_audio_codec_combo)
        custom_preferences_row.addStretch(1)

        self.custom_preferences_hint_label = BodyLabel(
            self.tr("自定义预设会按你的偏好组合下载格式，并保留自动回退策略。"),
            self.custom_preferences_section,
        )
        self.custom_preferences_hint_label.setObjectName("downloadHintLabel")
        self.custom_preferences_hint_label.setWordWrap(True)

        simple_layout.addLayout(simple_row)
        simple_layout.addWidget(self.simple_hint_label)
        custom_preferences_layout.addWidget(custom_preferences_title)
        custom_preferences_layout.addLayout(custom_preferences_row)
        custom_preferences_layout.addWidget(self.custom_preferences_hint_label)
        simple_layout.addWidget(self.custom_preferences_section)
        self.custom_preferences_section.setVisible(False)

        self.pr_smart_postprocess_checkbox = QCheckBox(
            self.tr("若下载结果为 AV1，则额外转为 H.265"),
            self.simple_panel,
        )
        self.pr_smart_postprocess_checkbox.setVisible(False)
        simple_layout.addWidget(self.pr_smart_postprocess_checkbox)
        self.pr_smart_transcript_checkbox = QCheckBox(
            self.tr("生成视频文稿（使用 YouTube 字幕）"),
            self.simple_panel,
        )
        self.pr_smart_transcript_checkbox.setVisible(False)
        simple_layout.addWidget(self.pr_smart_transcript_checkbox)

        self.professional_panel = QWidget(self.selection_section)
        professional_layout = QVBoxLayout(self.professional_panel)
        professional_layout.setContentsMargins(0, 0, 0, 0)
        professional_layout.setSpacing(10)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        self.professional_mode_label = BodyLabel(self.tr("下载模式"), self.professional_panel)
        self.professional_mode_label.setObjectName("downloadPrimaryLabel")
        self.professional_mode_combo = ComboBox(self.professional_panel)
        for key, text in self.PROFESSIONAL_MODES:
            self.professional_mode_combo.addItem(text, userData=key)
        self.professional_mode_combo.setMinimumWidth(200)
        mode_row.addWidget(self.professional_mode_label)
        mode_row.addWidget(self.professional_mode_combo)
        mode_row.addStretch(1)
        self.video_section_title = BodyLabel(self.tr("视频流"), self.professional_panel)
        self.video_section_title.setObjectName("downloadPrimaryLabel")
        self.audio_section_title = BodyLabel(self.tr("音频流"), self.professional_panel)
        self.audio_section_title.setObjectName("downloadPrimaryLabel")
        self.video_table = self._create_format_table(self.professional_panel)
        self.audio_table = self._create_format_table(self.professional_panel)
        professional_layout.addLayout(mode_row)
        professional_layout.addWidget(self.video_section_title)
        professional_layout.addWidget(self.video_table)
        professional_layout.addWidget(self.audio_section_title)
        professional_layout.addWidget(self.audio_table)

        self.mode_stack.addWidget(self.simple_panel)
        self.mode_stack.addWidget(self.professional_panel)
        self.selection_summary_label = BodyLabel(self.tr("已选方案：暂无"), self.selection_section)
        self.selection_summary_label.setObjectName("downloadPrimaryLabel")
        self.selection_summary_label.setWordWrap(True)
        selection_layout.addWidget(self.mode_switch)
        selection_layout.addWidget(self.mode_stack)
        selection_layout.addWidget(self.selection_summary_label)

        parent_layout.addWidget(self.selection_section)

    def _setup_separator(self, parent_layout):
        separator = QFrame(self.config_card)
        separator.setFrameShape(QFrame.HLine)
        separator.setObjectName("downloadSeparator")
        separator.setFixedHeight(1)
        parent_layout.addWidget(separator)

    def _setup_options_section(self, parent_layout):
        self.options_section = QWidget()
        options_layout = QVBoxLayout(self.options_section)
        options_layout.setContentsMargins(20, 12, 20, 16)
        options_layout.setSpacing(12)

        options_header = QHBoxLayout()
        options_header.setSpacing(18)
        options_title = BodyLabel(self.tr("附加下载项"), self.options_section)
        options_title.setObjectName("downloadSectionTitle")
        self.subtitle_checkbox = QCheckBox(self.tr("下载字幕"), self.options_section)
        self.thumbnail_checkbox = QCheckBox(self.tr("下载封面"), self.options_section)
        self.metadata_checkbox = QCheckBox(self.tr("下载元数据"), self.options_section)
        self.description_txt_checkbox = QCheckBox(self.tr("生成说明TXT"), self.options_section)
        self.description_txt_checkbox.setChecked(True)
        self.thumbnail_checkbox.setChecked(True)
        options_header.addWidget(options_title)
        options_header.addWidget(self.subtitle_checkbox)
        options_header.addWidget(self.thumbnail_checkbox)
        options_header.addWidget(self.metadata_checkbox)
        options_header.addWidget(self.description_txt_checkbox)
        options_header.addStretch(1)

        self.subtitle_mode_row = QWidget(self.options_section)
        subtitle_mode_layout = QHBoxLayout(self.subtitle_mode_row)
        subtitle_mode_layout.setContentsMargins(0, 0, 0, 0)
        subtitle_mode_layout.setSpacing(12)
        self.subtitle_mode_label = BodyLabel(self.tr("字幕来源"), self.subtitle_mode_row)
        self.subtitle_mode_label.setObjectName("downloadPrimaryLabel")
        self.subtitle_mode_combo = ComboBox(self.subtitle_mode_row)
        self.subtitle_mode_combo.addItem(self.tr("人工字幕"), userData="manual")
        self.subtitle_mode_combo.addItem(self.tr("自动字幕"), userData="auto")
        self.subtitle_mode_combo.setMinimumWidth(140)
        subtitle_mode_layout.addWidget(self.subtitle_mode_label)
        subtitle_mode_layout.addWidget(self.subtitle_mode_combo)
        subtitle_mode_layout.addStretch(1)

        self.time_range_section = QWidget(self.options_section)
        time_range_layout = QVBoxLayout(self.time_range_section)
        time_range_layout.setContentsMargins(0, 0, 0, 0)
        time_range_layout.setSpacing(8)

        time_range_header = QHBoxLayout()
        time_range_header.setContentsMargins(0, 0, 0, 0)
        time_range_header.setSpacing(12)
        self.enable_time_ranges_checkbox = QCheckBox(self.tr("启用时间段下载"), self.time_range_section)
        self.multi_time_ranges_checkbox = QCheckBox(self.tr("多时间段"), self.time_range_section)
        self.multi_time_ranges_checkbox.setEnabled(False)
        time_range_header.addWidget(self.enable_time_ranges_checkbox)
        time_range_header.addWidget(self.multi_time_ranges_checkbox)
        time_range_header.addStretch(1)

        self.time_range_hint_label = BodyLabel(
            self.tr("支持 MM:SS 或 HH:MM:SS；时间段仅作用于主媒体下载。"),
            self.time_range_section,
        )
        self.time_range_hint_label.setObjectName("downloadHintLabel")
        self.time_range_hint_label.setWordWrap(True)

        self.time_ranges_container = QWidget(self.time_range_section)
        self.time_ranges_layout = QVBoxLayout(self.time_ranges_container)
        self.time_ranges_layout.setContentsMargins(0, 0, 0, 0)
        self.time_ranges_layout.setSpacing(8)

        self.add_time_range_button = PushButton(self.tr("添加时间段"), self.time_range_section)
        self.add_time_range_button.setMaximumWidth(120)

        time_range_layout.addLayout(time_range_header)
        time_range_layout.addWidget(self.time_range_hint_label)
        time_range_layout.addWidget(self.time_ranges_container)
        time_range_layout.addWidget(self.add_time_range_button, 0, Qt.AlignLeft)

        self._add_time_range_row()
        self._update_time_range_ui_state()

        self.output_dir_row = QWidget(self.options_section)
        output_dir_layout = QHBoxLayout(self.output_dir_row)
        output_dir_layout.setContentsMargins(0, 0, 0, 0)
        output_dir_layout.setSpacing(12)
        self.output_dir_title = BodyLabel(self.tr("输出目录"), self.output_dir_row)
        self.output_dir_title.setObjectName("downloadPrimaryLabel")
        self.output_dir_value = BodyLabel("", self.output_dir_row)
        self.output_dir_value.setObjectName("downloadPathValueLabel")
        self.output_dir_value.setWordWrap(True)
        self.choose_output_dir_button = PushButton(self.tr("选择目录"), self.output_dir_row)
        self.reset_output_dir_button = PushButton(self.tr("跟随工作目录"), self.output_dir_row)
        output_dir_layout.addWidget(self.output_dir_title)
        output_dir_layout.addWidget(self.output_dir_value, 1)
        output_dir_layout.addWidget(self.choose_output_dir_button)
        output_dir_layout.addWidget(self.reset_output_dir_button)

        self.strategy_label = BodyLabel("", self.options_section)
        self.strategy_label.setObjectName("downloadHintLabel")
        self.strategy_label.setWordWrap(True)

        options_layout.addLayout(options_header)
        options_layout.addWidget(self.subtitle_mode_row)
        options_layout.addWidget(self.time_range_section)
        options_layout.addWidget(self.output_dir_row)
        options_layout.addWidget(self.strategy_label)

        parent_layout.addWidget(self.options_section)

    def _setup_result_area(self):
        self.result_card = CardWidget(self)
        self.result_card.setObjectName("downloadResultPanel")
        result_layout = QVBoxLayout(self.result_card)
        result_layout.setContentsMargins(20, 16, 20, 16)
        result_layout.setSpacing(8)

        result_header = QHBoxLayout()
        self.result_title = BodyLabel(self.tr("下载结果"), self.result_card)
        self.result_title.setObjectName("downloadSectionTitle")
        result_header.addWidget(self.result_title)
        result_header.addStretch(1)

        self.result_summary = BodyLabel("", self.result_card)
        self.result_summary.setWordWrap(True)
        self.result_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_summary.setObjectName("downloadPathValueLabel")

        result_details = QHBoxLayout()
        result_details.setSpacing(24)
        self.result_work_dir = BodyLabel("", self.result_card)
        self.result_work_dir.setWordWrap(True)
        self.result_work_dir.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_work_dir.setObjectName("downloadPathValueLabel")
        self.result_media = BodyLabel("", self.result_card)
        self.result_media.setWordWrap(True)
        self.result_media.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_media.setObjectName("downloadPathValueLabel")
        result_details.addWidget(self.result_work_dir, 1)
        result_details.addWidget(self.result_media, 1)

        result_files = QHBoxLayout()
        result_files.setSpacing(16)
        self.result_video = BodyLabel("", self.result_card)
        self.result_video.setWordWrap(True)
        self.result_video.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_video.setObjectName("downloadPathValueLabel")
        self.result_audio = BodyLabel("", self.result_card)
        self.result_audio.setWordWrap(True)
        self.result_audio.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_audio.setObjectName("downloadPathValueLabel")
        self.result_subtitle = BodyLabel("", self.result_card)
        self.result_subtitle.setWordWrap(True)
        self.result_subtitle.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_subtitle.setObjectName("downloadPathValueLabel")
        self.result_thumbnail = BodyLabel("", self.result_card)
        self.result_thumbnail.setWordWrap(True)
        self.result_thumbnail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_thumbnail.setObjectName("downloadPathValueLabel")
        self.result_metadata = BodyLabel("", self.result_card)
        self.result_metadata.setWordWrap(True)
        self.result_metadata.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_metadata.setObjectName("downloadPathValueLabel")
        self.result_description_txt = BodyLabel("", self.result_card)
        self.result_description_txt.setWordWrap(True)
        self.result_description_txt.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_description_txt.setObjectName("downloadPathValueLabel")
        self.result_transcript_txt = BodyLabel("", self.result_card)
        self.result_transcript_txt.setWordWrap(True)
        self.result_transcript_txt.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_transcript_txt.setObjectName("downloadPathValueLabel")
        self.result_terms_txt = BodyLabel("", self.result_card)
        self.result_terms_txt.setWordWrap(True)
        self.result_terms_txt.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_terms_txt.setObjectName("downloadPathValueLabel")
        self.result_transcoded = BodyLabel("", self.result_card)
        self.result_transcoded.setWordWrap(True)
        self.result_transcoded.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_transcoded.setObjectName("downloadPathValueLabel")
        result_files.addWidget(self.result_video, 1)
        result_files.addWidget(self.result_audio, 1)
        result_files.addWidget(self.result_subtitle, 1)

        result_files2 = QHBoxLayout()
        result_files2.setSpacing(16)
        result_files2.addWidget(self.result_thumbnail, 1)
        result_files2.addWidget(self.result_metadata, 1)
        result_files2.addWidget(self.result_description_txt, 1)

        result_files3 = QHBoxLayout()
        result_files3.setSpacing(16)
        result_files3.addWidget(self.result_transcript_txt, 1)
        result_files3.addWidget(self.result_terms_txt, 1)
        result_files3.addWidget(self.result_transcoded, 1)

        result_layout.addLayout(result_header)
        result_layout.addWidget(self.result_summary)
        result_layout.addLayout(result_details)
        result_layout.addLayout(result_files)
        result_layout.addLayout(result_files2)
        result_layout.addLayout(result_files3)

        self.result_card.setVisible(False)
        self.main_layout.addWidget(self.result_card)

    def _setup_bottom_bar(self):
        self.bottom_layout = QHBoxLayout()
        self.bottom_layout.setSpacing(12)
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setValue(0)
        self.status_label = BodyLabel(self.tr("等待解析链接"), self)
        self.status_label.setObjectName("downloadHintLabel")
        self.status_label.setMinimumWidth(120)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.download_detail_button = PushButton(self.tr("详情"), self)
        self.download_detail_button.setFixedHeight(30)
        self.download_detail_button.setFixedWidth(64)
        self.download_detail_panel = BodyLabel(self.tr("暂无实时下载数据"), self)
        self.download_detail_panel.setObjectName("downloadPathValueLabel")
        self.download_detail_panel.setWordWrap(True)
        self.download_detail_panel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.download_detail_panel.setVisible(False)
        self.bottom_layout.addWidget(self.progress_bar, 1)
        self.bottom_layout.addWidget(self.status_label)
        self.bottom_layout.addWidget(self.download_detail_button)
        self.main_layout.addLayout(self.bottom_layout)
        self.main_layout.addWidget(self.download_detail_panel)

    def _create_format_table(self, parent: QWidget) -> QTableWidget:
        table = QTableWidget(parent)
        table.setObjectName("downloadFormatTable")
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels([self.tr("选择"), self.tr("质量"), self.tr("详情")])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.setMinimumHeight(120)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return table

    def setup_signals(self):
        self.url_input.textChanged.connect(self._on_url_text_changed)
        self.parse_button.clicked.connect(self.parse_link)
        self.start_button.clicked.connect(self._on_start_button_clicked)
        self.subtitle_checkbox.toggled.connect(self._toggle_subtitle_mode_row)
        self.subtitle_checkbox.toggled.connect(self._refresh_selection_summary)
        self.thumbnail_checkbox.toggled.connect(self._refresh_selection_summary)
        self.metadata_checkbox.toggled.connect(self._refresh_selection_summary)
        self.description_txt_checkbox.toggled.connect(self._refresh_selection_summary)
        self.subtitle_checkbox.toggled.connect(self._save_download_preferences)
        self.thumbnail_checkbox.toggled.connect(self._save_download_preferences)
        self.metadata_checkbox.toggled.connect(self._save_download_preferences)
        self.description_txt_checkbox.toggled.connect(self._save_download_preferences)
        self.choose_output_dir_button.clicked.connect(self._choose_output_dir)
        self.reset_output_dir_button.clicked.connect(self._reset_output_dir)
        self.simple_preset_combo.currentIndexChanged.connect(self._on_simple_preset_changed)
        self.professional_mode_combo.currentIndexChanged.connect(self._on_professional_mode_changed)
        self.enable_time_ranges_checkbox.toggled.connect(self._on_enable_time_ranges_toggled)
        self.multi_time_ranges_checkbox.toggled.connect(self._on_multi_time_ranges_toggled)
        self.add_time_range_button.clicked.connect(self._on_add_time_range_clicked)
        self.custom_video_codec_combo.currentIndexChanged.connect(self._refresh_selection_summary)
        self.custom_container_combo.currentIndexChanged.connect(self._refresh_selection_summary)
        self.custom_audio_codec_combo.currentIndexChanged.connect(self._refresh_selection_summary)
        self.pr_smart_postprocess_checkbox.toggled.connect(self._refresh_selection_summary)
        self.pr_smart_transcript_checkbox.toggled.connect(self._on_pr_smart_transcript_toggled)
        self.subtitle_mode_combo.currentIndexChanged.connect(self._save_download_preferences)
        self.custom_video_codec_combo.currentIndexChanged.connect(self._save_download_preferences)
        self.custom_container_combo.currentIndexChanged.connect(self._save_download_preferences)
        self.custom_audio_codec_combo.currentIndexChanged.connect(self._save_download_preferences)
        self.pr_smart_postprocess_checkbox.toggled.connect(self._save_download_preferences)
        self.pr_smart_transcript_checkbox.toggled.connect(self._save_download_preferences)
        self.download_detail_button.clicked.connect(self._toggle_download_detail_panel)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_theme_styles()
        self._refresh_download_strategy_hint()
        self._refresh_output_dir_labels()
        self._adjust_responsive_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_responsive_layout()

    def _apply_theme_styles(self):
        if isDarkTheme():
            primary_color = "#F5F5F5"
            hint_color = "#999999"
            value_color = "#D4D4D4"
            title_color = "#FFFFFF"
            separator_color = "rgba(255, 255, 255, 0.08)"
            table_header_background = "rgba(255, 255, 255, 0.06)"
            table_grid = "rgba(255, 255, 255, 0.06)"
            thumbnail_bg = "rgba(255, 255, 255, 0.04)"
            thumbnail_border = "rgba(255, 255, 255, 0.08)"
        else:
            primary_color = "#1F1F1F"
            hint_color = "#8A8A8A"
            value_color = "#5F6368"
            title_color = "#1F1F1F"
            separator_color = "rgba(0, 0, 0, 0.08)"
            table_header_background = "rgba(0, 0, 0, 0.04)"
            table_grid = "rgba(0, 0, 0, 0.06)"
            thumbnail_bg = "rgba(0, 0, 0, 0.03)"
            thumbnail_border = "rgba(0, 0, 0, 0.08)"

        self.setStyleSheet(f"""
            QWidget#DownloadCenterInterface {{ background: transparent; }}
            QWidget#downloadScrollContent {{
                background: transparent;
            }}
            QScrollArea#downloadContentScroll {{
                background: transparent;
                border: none;
            }}
            QLabel#downloadTitleLabel {{
                color: {title_color};
                font-size: 15px;
                font-weight: 600;
            }}
            QLabel#downloadSectionTitle {{
                color: {title_color};
                font-size: 14px;
                font-weight: 600;
            }}
            QLabel#downloadPrimaryLabel {{ color: {primary_color}; }}
            QLabel#downloadHintLabel {{ color: {hint_color}; font-size: 13px; }}
            QLabel#downloadPathValueLabel {{ color: {value_color}; font-size: 13px; }}
            QCheckBox {{
                color: {primary_color};
                spacing: 6px;
            }}
            QCheckBox:disabled {{
                color: {hint_color};
            }}
            QLabel#downloadThumbnailLabel {{
                color: {hint_color};
                border: 1px solid {thumbnail_border};
                border-radius: 8px;
                background-color: {thumbnail_bg};
            }}
            QFrame#downloadSeparator {{
                background-color: {separator_color};
                border: none;
            }}
            QTableWidget#downloadFormatTable {{
                background: transparent;
                color: {value_color};
                gridline-color: {table_grid};
                border: 1px solid {separator_color};
                border-radius: 8px;
            }}
            QHeaderView::section {{
                background: {table_header_background};
                color: {primary_color};
                border: none;
                padding: 6px;
                font-size: 13px;
            }}
        """)

    def _switch_download_mode(self, mode_key: str):
        if mode_key not in {"simple", "professional"}:
            mode_key = "simple"
        self.current_mode_key = mode_key
        self.mode_switch.setCurrentItem(mode_key)
        self.mode_stack.setCurrentWidget(self.simple_panel if mode_key == "simple" else self.professional_panel)
        self._update_custom_preferences_visibility()
        self._refresh_selection_summary()
        self._save_download_preferences()

    @staticmethod
    def _set_combo_current_data(combo: ComboBox, value: str, default: str):
        target = str(value or default)
        default_index = 0
        for index in range(combo.count()):
            item_data = str(combo.itemData(index) or "")
            if item_data == default:
                default_index = index
            if item_data == target:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(default_index)

    def _restore_download_preferences(self):
        self._set_combo_current_data(
            self.simple_preset_combo,
            str(cfg.get(cfg.download_center_simple_preset) or "best_quality"),
            "best_quality",
        )
        self._set_combo_current_data(
            self.professional_mode_combo,
            str(cfg.get(cfg.download_center_professional_mode) or "video_audio"),
            "video_audio",
        )
        self._set_combo_current_data(
            self.subtitle_mode_combo,
            str(cfg.get(cfg.download_center_subtitle_mode) or "manual"),
            "manual",
        )
        self._set_combo_current_data(
            self.custom_video_codec_combo,
            str(cfg.get(cfg.download_center_custom_video_codec) or "auto"),
            "auto",
        )
        self._set_combo_current_data(
            self.custom_container_combo,
            str(cfg.get(cfg.download_center_custom_container) or "auto"),
            "auto",
        )
        self._set_combo_current_data(
            self.custom_audio_codec_combo,
            str(cfg.get(cfg.download_center_custom_audio_codec) or "auto"),
            "auto",
        )

        self.subtitle_checkbox.setChecked(bool(cfg.get(cfg.download_center_need_subtitle)))
        self.thumbnail_checkbox.setChecked(bool(cfg.get(cfg.download_center_need_thumbnail)))
        self.metadata_checkbox.setChecked(bool(cfg.get(cfg.download_center_need_metadata)))
        self.description_txt_checkbox.setChecked(bool(cfg.get(cfg.download_center_need_description_txt)))
        self.pr_smart_postprocess_checkbox.setChecked(bool(cfg.get(cfg.download_center_pr_smart_postprocess)))
        self.pr_smart_transcript_checkbox.setChecked(bool(cfg.get(cfg.download_center_pr_smart_transcript_txt)))

        mode_key = str(cfg.get(cfg.download_center_mode) or "simple")
        self._switch_download_mode(mode_key)
        self._on_professional_mode_changed()
        self._toggle_subtitle_mode_row(self.subtitle_checkbox.isChecked())

    def _save_download_preferences(self, *_args):
        if self._restoring_download_preferences:
            return
        cfg.set(cfg.download_center_mode, self.current_mode_key)
        cfg.set(cfg.download_center_simple_preset, self.simple_preset_combo.currentData() or "best_quality")
        cfg.set(cfg.download_center_professional_mode, self.professional_mode_combo.currentData() or "video_audio")
        cfg.set(cfg.download_center_need_subtitle, self.subtitle_checkbox.isChecked())
        cfg.set(cfg.download_center_need_thumbnail, self.thumbnail_checkbox.isChecked())
        cfg.set(cfg.download_center_need_metadata, self.metadata_checkbox.isChecked())
        cfg.set(cfg.download_center_need_description_txt, self.description_txt_checkbox.isChecked())
        cfg.set(cfg.download_center_subtitle_mode, self._selected_subtitle_mode())
        cfg.set(cfg.download_center_custom_video_codec, self.custom_video_codec_combo.currentData() or "auto")
        cfg.set(cfg.download_center_custom_container, self.custom_container_combo.currentData() or "auto")
        cfg.set(cfg.download_center_custom_audio_codec, self.custom_audio_codec_combo.currentData() or "auto")
        cfg.set(cfg.download_center_pr_smart_postprocess, self.pr_smart_postprocess_checkbox.isChecked())
        cfg.set(cfg.download_center_pr_smart_transcript_txt, self.pr_smart_transcript_checkbox.isChecked())

    def _set_preview_visible(self, visible: bool):
        self.preview_card.setVisible(visible)
        self.config_card.setVisible(visible)
        self.start_button.setEnabled(visible)
        self._adjust_responsive_layout()

    def _adjust_responsive_layout(self):
        if not hasattr(self, "video_table") or not hasattr(self, "audio_table"):
            return

        try:
            if hasattr(self, "preview_card_layout"):
                if self.width() < 640:
                    self.preview_card_layout.setDirection(QBoxLayout.TopToBottom)
                    self.thumbnail_label.setMaximumWidth(16777215)
                    self.thumbnail_label.setMaximumHeight(180)
                else:
                    self.preview_card_layout.setDirection(QBoxLayout.LeftToRight)
                    self.thumbnail_label.setMaximumWidth(280)
                    self.thumbnail_label.setMaximumHeight(16777215)
        except Exception:
            pass

        visible_tables = int(self.video_table.isVisible()) + int(self.audio_table.isVisible())
        if visible_tables <= 0:
            return

        height = max(self.height(), 520)
        total_budget = max(220, min(520, height - 380))
        per_table_height = max(120, min(320, total_budget // visible_tables))
        if self.video_table.isVisible():
            self.video_table.setMinimumHeight(per_table_height)
        if self.audio_table.isVisible():
            self.audio_table.setMinimumHeight(per_table_height)

    def _set_controls_enabled(self, enabled: bool):
        self.controls_enabled = enabled
        self.url_input.setEnabled(enabled)
        self.parse_button.setEnabled(enabled)
        self.simple_preset_combo.setEnabled(enabled)
        self.professional_mode_combo.setEnabled(enabled)
        self.subtitle_checkbox.setEnabled(enabled)
        self.thumbnail_checkbox.setEnabled(enabled)
        self.metadata_checkbox.setEnabled(enabled)
        self.description_txt_checkbox.setEnabled(enabled)
        subtitle_source_needed = self.subtitle_checkbox.isChecked() or (
            self._is_pr_smart_preset_selected() and self.pr_smart_transcript_checkbox.isChecked()
        )
        self.subtitle_mode_combo.setEnabled(enabled and subtitle_source_needed)
        self.choose_output_dir_button.setEnabled(enabled)
        self.reset_output_dir_button.setEnabled(enabled)
        self.custom_video_codec_combo.setEnabled(enabled and self._is_custom_simple_preset_selected())
        self.custom_container_combo.setEnabled(enabled and self._is_custom_simple_preset_selected())
        self.custom_audio_codec_combo.setEnabled(enabled and self._is_custom_simple_preset_selected())
        self._update_time_range_ui_state()
        self._update_custom_preferences_visibility()
        self._refresh_start_button_state()
        self.video_table.setEnabled(enabled)
        self.audio_table.setEnabled(enabled)

    def _refresh_start_button_state(self):
        if self.download_action_state == "downloading":
            self.start_button.setText(self.tr("暂停下载"))
            self.start_button.setToolTip(self.tr("点击后先暂停下载"))
            self.start_button.setEnabled(True)
            return

        if self.download_action_state == "paused":
            self.start_button.setText(self.tr("终止下载"))
            self.start_button.setToolTip(self.tr("再次点击将终止下载并清理当前数据"))
            self.start_button.setEnabled(True)
            return

        if self.download_action_state == "terminating":
            self.start_button.setText(self.tr("终止中…"))
            self.start_button.setToolTip(self.tr("正在终止下载并清理当前数据"))
            self.start_button.setEnabled(False)
            return

        self.start_button.setText(self.tr("开始下载"))
        self.start_button.setToolTip("")
        self.start_button.setEnabled(self.controls_enabled and self.preview_data is not None)

    def _set_download_action_state(self, state: str):
        self.download_action_state = state
        self._refresh_start_button_state()

    def _on_start_button_clicked(self):
        if self.download_action_state == "idle":
            self.start_download()
            return

        if not self.download_thread or not self.download_thread.isRunning():
            self.download_thread = None
            self._set_download_action_state("idle")
            return

        if self.download_action_state == "downloading":
            self.download_thread.request_pause()
            self._set_download_action_state("paused")
            self.status_label.setText(self.tr("正在暂停下载，暂停后再次点击将终止并清理当前数据…"))
            return

        if self.download_action_state == "paused":
            self.download_thread.request_terminate()
            self._set_download_action_state("terminating")
            self.status_label.setText(self.tr("正在终止下载并清理当前数据…"))

    def _set_result_actions_enabled(self, enabled: bool, has_video: bool = False):
        self.open_folder_action.setEnabled(enabled)
        self.send_to_transcription_action.setEnabled(enabled and has_video)

    def _toggle_download_detail_panel(self):
        visible = not self.download_detail_panel.isVisible()
        self.download_detail_panel.setVisible(visible)
        self.download_detail_button.setText(self.tr("收起") if visible else self.tr("详情"))
        self._adjust_responsive_layout()

    def _reset_download_detail_panel(self):
        self.latest_download_detail = {}
        self.download_detail_panel.setText(self.tr("暂无实时下载数据"))
        self.download_detail_panel.setVisible(False)
        self.download_detail_button.setText(self.tr("详情"))

    def _render_download_detail_panel(self, detail: dict):
        self.latest_download_detail = detail or {}
        if not self.latest_download_detail:
            self.download_detail_panel.setText(self.tr("暂无实时下载数据"))
            return

        parts = []
        filename = str(self.latest_download_detail.get("filename") or "").strip()
        if filename:
            parts.append(self.tr("文件：") + filename)

        amount = str(self.latest_download_detail.get("downloaded") or "").strip()
        total = str(self.latest_download_detail.get("total") or "").strip()
        if amount or total:
            progress_text = amount
            if total:
                progress_text = f"{amount or '?'} / {total}"
            parts.append(self.tr("已下载：") + progress_text)

        percent = str(self.latest_download_detail.get("percent") or "").strip()
        speed = str(self.latest_download_detail.get("speed") or "").strip()
        eta = str(self.latest_download_detail.get("eta") or "").strip()
        elapsed = str(self.latest_download_detail.get("elapsed") or "").strip()
        if percent:
            parts.append(self.tr("进度：") + percent + "%")
        if speed:
            parts.append(self.tr("速度：") + speed)
        if eta:
            parts.append(self.tr("剩余：") + eta)
        if elapsed:
            parts.append(self.tr("已用时：") + elapsed)

        self.download_detail_panel.setText("\n".join(parts) if parts else self.tr("暂无实时下载数据"))

    def _reset_result_labels(self):
        self.result_summary.setText(self.tr("方案摘要：暂无"))
        self.result_work_dir.setText(self.tr("输出目录：暂无"))
        self.result_media.setText(self.tr("主媒体：暂无"))
        self.result_video.setText(self.tr("视频：暂无"))
        self.result_audio.setText(self.tr("音频：暂无"))
        self.result_subtitle.setText(self.tr("字幕：暂无"))
        self.result_thumbnail.setText(self.tr("封面：暂无"))
        self.result_metadata.setText(self.tr("元数据：暂无"))
        self.result_description_txt.setText(self.tr("说明TXT：暂无"))
        self.result_transcript_txt.setText(self.tr("视频文稿：暂无"))
        self.result_terms_txt.setText(self.tr("AI术语表：请在 WhisperX 热词管理中手动生成"))
        self.result_transcoded.setText(self.tr("H.265后处理：暂无"))

    def _reset_preview_labels(self):
        self.preview_title_label.setText(self.tr("标题：暂无"))
        self.preview_uploader_label.setText(self.tr("作者：暂无"))
        self.preview_meta_label.setText(self.tr("时长 / 日期 / 播放量：暂无"))
        self.preview_subtitle_label.setText(self.tr("字幕：暂无"))
        self.thumbnail_label.setPixmap(QPixmap())
        self.thumbnail_label.setText(self.tr("暂无封面"))

    def _clear_preview(self):
        self.preview_data = None
        self.parsed_url = ""
        self.selected_video_format = None
        self.selected_audio_format = None
        self._reset_preview_labels()
        self._clear_table(self.video_table)
        self._clear_table(self.audio_table)
        self._set_preview_visible(False)
        self._refresh_selection_summary()

    def _clear_table(self, table: QTableWidget):
        table.setRowCount(0)
        table.clearContents()

    def _on_url_text_changed(self, *_args):
        current_url = self.url_input.text().strip()
        if self.preview_data and current_url != self.parsed_url:
            self.status_label.setText(self.tr("链接已变更，请重新解析"))
            self._clear_preview()

    def _toggle_subtitle_mode_row(self, checked: bool | None = None):
        subtitle_source_needed = self.subtitle_checkbox.isChecked() or (
            self._is_pr_smart_preset_selected() and self.pr_smart_transcript_checkbox.isChecked()
        )
        self.subtitle_mode_row.setVisible(subtitle_source_needed)
        self.subtitle_mode_combo.setEnabled(self.controls_enabled and subtitle_source_needed)
        self._refresh_selection_summary()

    def _is_custom_simple_preset_selected(self) -> bool:
        return (self.simple_preset_combo.currentData() or "") == "custom_preferences"

    def _is_pr_smart_preset_selected(self) -> bool:
        return (self.simple_preset_combo.currentData() or "") in {"pr_smart", "pr_editing"}

    def _update_custom_preferences_visibility(self):
        is_custom = self._is_custom_simple_preset_selected()
        self.custom_preferences_section.setVisible(is_custom)
        self.custom_video_codec_combo.setEnabled(self.controls_enabled and is_custom)
        self.custom_container_combo.setEnabled(self.controls_enabled and is_custom)
        self.custom_audio_codec_combo.setEnabled(self.controls_enabled and is_custom)
        is_pr_smart = self._is_pr_smart_preset_selected()
        self.pr_smart_postprocess_checkbox.setVisible(is_pr_smart)
        self.pr_smart_postprocess_checkbox.setEnabled(self.controls_enabled and is_pr_smart)
        self.pr_smart_transcript_checkbox.setVisible(is_pr_smart)
        self.pr_smart_transcript_checkbox.setEnabled(self.controls_enabled and is_pr_smart)
        self._toggle_subtitle_mode_row()

    def _on_simple_preset_changed(self, *_args):
        self._update_custom_preferences_visibility()
        self._refresh_selection_summary()
        self._save_download_preferences()

    def _on_pr_smart_transcript_toggled(self, *_args):
        self._toggle_subtitle_mode_row()
        self._refresh_selection_summary()

    def _create_time_range_row(self, start_text: str = "", end_text: str = "") -> dict:
        row_widget = QWidget(self.time_ranges_container)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        start_input = LineEdit(row_widget)
        start_input.setPlaceholderText(self.tr("开始时间，如 01:30"))
        start_input.setText(start_text)
        end_input = LineEdit(row_widget)
        end_input.setPlaceholderText(self.tr("结束时间，如 03:10"))
        end_input.setText(end_text)
        delete_button = PushButton(self.tr("删除"), row_widget)
        delete_button.setMaximumWidth(72)

        row_layout.addWidget(BodyLabel(self.tr("开始"), row_widget))
        row_layout.addWidget(start_input, 1)
        row_layout.addWidget(BodyLabel(self.tr("结束"), row_widget))
        row_layout.addWidget(end_input, 1)
        row_layout.addWidget(delete_button)

        row = {
            "widget": row_widget,
            "start_input": start_input,
            "end_input": end_input,
            "delete_button": delete_button,
        }
        start_input.textChanged.connect(self._refresh_selection_summary)
        end_input.textChanged.connect(self._refresh_selection_summary)
        delete_button.clicked.connect(lambda: self._remove_time_range_row(row))
        return row

    def _add_time_range_row(self, start_text: str = "", end_text: str = ""):
        row = self._create_time_range_row(start_text, end_text)
        self.time_range_rows.append(row)
        self.time_ranges_layout.addWidget(row["widget"])
        self._update_time_range_ui_state()

    def _remove_time_range_row(self, row: dict):
        if len(self.time_range_rows) <= 1:
            row["start_input"].clear()
            row["end_input"].clear()
            self._refresh_selection_summary()
            return

        self.time_range_rows.remove(row)
        row["widget"].setParent(None)
        row["widget"].deleteLater()
        self._update_time_range_ui_state()
        self._refresh_selection_summary()

    def _visible_time_range_rows(self) -> list[dict]:
        if not self.time_range_rows:
            return []
        if self.multi_time_ranges_checkbox.isChecked():
            return self.time_range_rows
        return self.time_range_rows[:1]

    def _update_time_range_ui_state(self):
        enabled = self.enable_time_ranges_checkbox.isChecked()
        multi_enabled = enabled and self.multi_time_ranges_checkbox.isChecked()
        effective_enabled = self.controls_enabled and enabled
        self.enable_time_ranges_checkbox.setEnabled(self.controls_enabled)
        self.multi_time_ranges_checkbox.setEnabled(self.controls_enabled and enabled)
        self.time_range_hint_label.setVisible(enabled)
        self.time_ranges_container.setVisible(enabled)
        self.add_time_range_button.setVisible(multi_enabled)
        self.add_time_range_button.setEnabled(self.controls_enabled and multi_enabled)

        visible_rows = self._visible_time_range_rows()
        visible_count = len(visible_rows)
        for index, row in enumerate(self.time_range_rows):
            row_visible = enabled and (multi_enabled or index == 0)
            row["widget"].setVisible(row_visible)
            row["delete_button"].setVisible(multi_enabled and row_visible and visible_count > 1)
            row["start_input"].setEnabled(effective_enabled and row_visible)
            row["end_input"].setEnabled(effective_enabled and row_visible)
            row["delete_button"].setEnabled(self.controls_enabled and multi_enabled and row_visible and visible_count > 1)

    def _on_enable_time_ranges_toggled(self, _checked: bool):
        self._update_time_range_ui_state()
        self._refresh_selection_summary()

    def _on_multi_time_ranges_toggled(self, _checked: bool):
        self._update_time_range_ui_state()
        self._refresh_selection_summary()

    def _on_add_time_range_clicked(self):
        self._add_time_range_row()
        self._refresh_selection_summary()

    @staticmethod
    def _normalize_time_value(value: str) -> tuple[str, int] | None:
        text = str(value or "").strip()
        if not text:
            return None
        parts = text.split(":")
        if len(parts) not in {2, 3} or not all(part.isdigit() for part in parts):
            return None

        try:
            if len(parts) == 2:
                minutes, seconds = map(int, parts)
                hours = 0
            else:
                hours, minutes, seconds = map(int, parts)
        except ValueError:
            return None

        if minutes < 0 or seconds < 0 or seconds >= 60 or (len(parts) == 3 and minutes >= 60):
            return None

        total_seconds = hours * 3600 + minutes * 60 + seconds
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}", total_seconds

    def _preview_duration_seconds(self) -> int | None:
        if not self.preview_data:
            return None
        try:
            duration = self.preview_data.get("info_dict", {}).get("duration")
            if duration in (None, ""):
                return None
            return int(float(duration))
        except (TypeError, ValueError):
            return None

    def _time_range_summary_text(self) -> str:
        if not self.enable_time_ranges_checkbox.isChecked():
            return ""

        visible_rows = self._visible_time_range_rows()
        if not visible_rows:
            return self.tr("片段：待填写")

        normalized_ranges = []
        for row in visible_rows:
            start_data = self._normalize_time_value(row["start_input"].text())
            end_data = self._normalize_time_value(row["end_input"].text())
            if not start_data or not end_data:
                return self.tr("片段：待填写")
            normalized_ranges.append((start_data[0], end_data[0]))

        if len(normalized_ranges) == 1:
            start_text, end_text = normalized_ranges[0]
            return self.tr("片段：") + f"{start_text} - {end_text}"
        return self.tr("片段：") + self.tr(f"{len(normalized_ranges)} 段")

    def _collect_download_sections(self, need_video: bool) -> list[str] | None:
        if not self.enable_time_ranges_checkbox.isChecked():
            return []
        if not need_video:
            InfoBar.warning(self.tr("提示"), self.tr("时间段下载仅适用于主媒体下载。"), duration=3000, parent=self)
            return None

        total_duration = self._preview_duration_seconds()
        sections = []
        for index, row in enumerate(self._visible_time_range_rows(), start=1):
            start_text = row["start_input"].text().strip()
            end_text = row["end_input"].text().strip()
            if not start_text or not end_text:
                InfoBar.warning(self.tr("提示"), self.tr(f"请完整填写第 {index} 个时间段。"), duration=3000, parent=self)
                return None
            start_data = self._normalize_time_value(start_text)
            end_data = self._normalize_time_value(end_text)
            if not start_data or not end_data:
                InfoBar.warning(self.tr("提示"), self.tr(f"第 {index} 个时间段格式无效，请使用 MM:SS 或 HH:MM:SS。"), duration=3500, parent=self)
                return None
            if start_data[1] >= end_data[1]:
                InfoBar.warning(self.tr("提示"), self.tr(f"第 {index} 个时间段的开始时间必须早于结束时间。"), duration=3500, parent=self)
                return None
            if total_duration is not None and end_data[1] > total_duration:
                InfoBar.warning(self.tr("提示"), self.tr(f"第 {index} 个时间段超过了视频总时长。"), duration=3500, parent=self)
                return None
            sections.append(f"*{start_data[0]}-{end_data[0]}")
        return sections

    def _effective_output_dir(self) -> str:
        custom_dir = str(cfg.get(cfg.download_center_output_dir) or "").strip()
        return custom_dir or str(cfg.get(cfg.work_dir))

    def _refresh_output_dir_labels(self):
        self.output_dir_value.setText(self._effective_output_dir())

    def _refresh_download_strategy_hint(self):
        strategy = str(cfg.get(cfg.download_engine_strategy) or "智能选择")
        auto_cookie = bool(cfg.get(cfg.download_auto_refresh_edge_cookies))
        auto_cookie_text = self.tr("下载前自动刷新 Edge Cookie：开启") if auto_cookie else self.tr("下载前自动刷新 Edge Cookie：关闭")
        self.strategy_label.setText(self.tr("当前下载策略：") + strategy + "    " + auto_cookie_text)

    def _choose_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("选择下载输出目录"), self._effective_output_dir())
        if not folder:
            return
        cfg.set(cfg.download_center_output_dir, folder)
        self._refresh_output_dir_labels()

    def _reset_output_dir(self):
        cfg.set(cfg.download_center_output_dir, "")
        self._refresh_output_dir_labels()

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        try:
            parsed = urlparse(url.strip())
            return parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except ValueError:
            return False

    def _selected_subtitle_mode(self) -> str:
        return self.subtitle_mode_combo.currentData() or "manual"

    def _refresh_edge_cookie_if_needed(self):
        if not bool(cfg.get(cfg.download_auto_refresh_edge_cookies)):
            return
        result = export_edge_cookies()
        if result.get("success"):
            self.status_label.setText(self.tr("已刷新 Edge Cookie，继续处理链接…"))
            return
        message = result.get("message", self.tr("无法刷新 Edge Cookie，将继续尝试下载"))
        if result.get("needs_elevation_hint") and not result.get("is_elevated"):
            message += self.tr("；可尝试以管理员权限运行后重试")
        InfoBar.warning(self.tr("Cookie 刷新失败"), message, duration=4000, parent=self, position=InfoBarPosition.BOTTOM_RIGHT)

    def parse_link(self):
        url = self.url_input.text().strip()
        if not self._is_valid_url(url):
            InfoBar.error(self.tr("错误"), self.tr("请输入有效的视频 URL"), duration=3000, parent=self)
            return
        self._refresh_edge_cookie_if_needed()
        cookiefile_path = APPDATA_PATH / "cookies.txt"
        if not cookiefile_path.exists():
            InfoBar.warning(self.tr("提示"), self.tr("建议配置 cookies.txt，以提高高清视频与字幕的可用性。"), duration=4000, parent=self, position=InfoBarPosition.BOTTOM_RIGHT)
        self._set_controls_enabled(False)
        self._set_preview_visible(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr("正在解析链接…"))
        self.preview_thread = VideoPreviewThread(url=url, download_engine_strategy=str(cfg.get(cfg.download_engine_strategy) or "智能选择"))
        self.preview_thread.finished.connect(self.on_preview_finished)
        self.preview_thread.error.connect(self.on_preview_error)
        self.preview_thread.start()

    def on_preview_finished(self, preview: dict):
        self.preview_data = preview
        self.parsed_url = preview.get("url", self.url_input.text().strip())
        self._set_controls_enabled(True)
        self._set_preview_visible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr("解析完成，请选择下载方案"))
        self._render_preview_card(preview)
        self._populate_video_table(preview.get("video_formats") or [])
        self._populate_audio_table(preview.get("audio_formats") or [])
        self._adjust_responsive_layout()
        self._refresh_selection_summary()
        InfoBar.success(self.tr("解析完成"), self.tr("已获取可选格式，请确认下载方案。"), duration=2500, parent=self)

    def on_preview_error(self, error: str):
        self._set_controls_enabled(True)
        self._set_preview_visible(False)
        self.preview_data = None
        self.status_label.setText(self.tr("解析失败"))
        InfoBar.error(self.tr("解析失败"), error, duration=5000, parent=self)

    def _render_preview_card(self, preview: dict):
        self.preview_title_label.setText(self.tr("标题：") + str(preview.get("title") or "暂无"))
        self.preview_uploader_label.setText(self.tr("作者：") + str(preview.get("uploader") or "暂无"))
        meta_parts = [preview.get("duration_text") or "未知时长"]
        if preview.get("upload_date"):
            meta_parts.append(str(preview["upload_date"]))
        if preview.get("view_count_text"):
            meta_parts.append(str(preview["view_count_text"]) + self.tr(" 次观看"))
        self.preview_meta_label.setText(self.tr("时长 / 日期 / 播放量：") + " · ".join(meta_parts))
        manual = preview.get("manual_subtitle_languages") or []
        auto = preview.get("auto_subtitle_languages") or []
        subtitle_text = self.tr("字幕：人工 ") + (", ".join(manual) if manual else self.tr("无"))
        subtitle_text += self.tr("；自动 ") + (", ".join(auto) if auto else self.tr("无"))
        self.preview_subtitle_label.setText(subtitle_text)
        self.thumbnail_label.setPixmap(QPixmap())
        thumbnail_bytes = preview.get("thumbnail_bytes")
        if thumbnail_bytes:
            pixmap = QPixmap()
            pixmap.loadFromData(thumbnail_bytes)
            self.thumbnail_label.setPixmap(pixmap)
            self.thumbnail_label.setText("")
        else:
            self.thumbnail_label.setText(self.tr("暂无封面"))

    def _populate_video_table(self, formats: list[dict]):
        self.video_button_group = QButtonGroup(self)
        self.video_button_group.setExclusive(True)
        self.selected_video_format = None
        self._populate_format_table(self.video_table, formats, "video", self.video_button_group)

    def _populate_audio_table(self, formats: list[dict]):
        self.audio_button_group = QButtonGroup(self)
        self.audio_button_group.setExclusive(True)
        self.selected_audio_format = None
        self._populate_format_table(self.audio_table, formats, "audio", self.audio_button_group)

    def _populate_format_table(self, table: QTableWidget, formats: list[dict], kind: str, button_group: QButtonGroup):
        table.clearContents()
        try:
            table.cellClicked.disconnect()
        except TypeError:
            pass
        if not formats:
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem("-"))
            table.setItem(0, 1, QTableWidgetItem(self.tr("暂无可选格式")))
            table.setItem(0, 2, QTableWidgetItem(self.tr("当前资源未提供对应流")))
            return

        table.setRowCount(len(formats))
        for row, fmt in enumerate(formats):
            radio = QRadioButton(table)
            radio.toggled.connect(lambda checked, data=fmt, stream_kind=kind: self._on_format_selected(stream_kind, data, checked))
            button_group.addButton(radio, row)
            radio_container = QWidget(table)
            radio_layout = QHBoxLayout(radio_container)
            radio_layout.setContentsMargins(0, 0, 0, 0)
            radio_layout.addStretch(1)
            radio_layout.addWidget(radio)
            radio_layout.addStretch(1)
            table.setCellWidget(row, 0, radio_container)
            table.setItem(row, 1, QTableWidgetItem(fmt.get("quality") or self.tr("未知")))
            table.setItem(row, 2, QTableWidgetItem(fmt.get("details") or self.tr("暂无详情")))
        table.cellClicked.connect(lambda row, _column, group=button_group: self._activate_row_radio(group, row))
        table.resizeRowsToContents()

    @staticmethod
    def _activate_row_radio(button_group: QButtonGroup, row: int):
        button = button_group.button(row)
        if button:
            button.setChecked(True)

    def _on_format_selected(self, kind: str, fmt: dict, checked: bool):
        if not checked:
            return
        if kind == "video":
            self.selected_video_format = fmt
        else:
            self.selected_audio_format = fmt
        self._refresh_selection_summary()

    def _on_professional_mode_changed(self, *_args):
        mode = self.professional_mode_combo.currentData() or "video_audio"
        needs_video = mode in {"video", "video_audio"}
        needs_audio = mode in {"audio", "video_audio"}
        self.video_section_title.setVisible(needs_video)
        self.video_table.setVisible(needs_video)
        self.video_table.setEnabled(needs_video)
        self.audio_table.setEnabled(needs_audio)
        self.audio_section_title.setVisible(needs_audio)
        self.audio_table.setVisible(needs_audio)
        self._adjust_responsive_layout()
        self._refresh_selection_summary()
        self._save_download_preferences()

    def _describe_stream(self, stream: dict | None) -> str:
        if not stream:
            return self.tr("未选择")
        quality = stream.get("quality") or self.tr("未知")
        details = stream.get("details") or ""
        return f"{quality} · {details}" if details else str(quality)

    def _combine_selector_chains(self, selectors: list[str]) -> str:
        unique_selectors = []
        seen = set()
        for selector in selectors:
            normalized = str(selector or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_selectors.append(normalized)
        return "/".join(unique_selectors)

    @staticmethod
    def _codec_rank(codec: str, preferred_codecs: tuple[str, ...]) -> int:
        lowered = str(codec or "").lower()
        for index, item in enumerate(preferred_codecs):
            if item in lowered:
                return index
        return len(preferred_codecs)

    def _pick_pr_smart_video_format(self) -> dict | None:
        formats = list((self.preview_data or {}).get("video_formats") or [])
        if not formats:
            return None

        max_height = max(int(item.get("height") or 0) for item in formats)
        same_tier = [item for item in formats if int(item.get("height") or 0) == max_height] or formats
        preferred_codecs = ("hevc", "h265") if max_height <= 1080 else ("hevc", "h265", "av01", "av1", "avc1")
        same_tier.sort(
            key=lambda item: (
                self._codec_rank(item.get("vcodec"), preferred_codecs),
                -(int(item.get("fps") or 0)),
                -(int(item.get("filesize") or 0)),
            )
        )
        return same_tier[0]

    def _pick_pr_smart_audio_format(self) -> dict | None:
        formats = list((self.preview_data or {}).get("audio_formats") or [])
        if not formats:
            return None

        preferred = []
        fallback = []
        for item in formats:
            lowered_codec = str(item.get("acodec") or "").lower()
            lowered_ext = str(item.get("ext") or "").lower()
            target = preferred if ("mp4a" in lowered_codec or lowered_ext == "m4a") else fallback
            target.append(item)

        ranked = preferred or fallback
        ranked.sort(
            key=lambda item: (
                -(int(item.get("abr") or 0)),
                -(int(item.get("filesize") or 0)),
                -(int(item.get("channels") or 0)),
            )
        )
        return ranked[0] if ranked else None

    def _build_pr_smart_request(self) -> dict:
        video_format = self._pick_pr_smart_video_format()
        audio_format = self._pick_pr_smart_audio_format()
        if not video_format:
            return {
                "need_video": True,
                "download_mode": "video_audio",
                "selected_video_format_id": "",
                "selected_audio_format_id": "",
                "format_selector": "bestvideo+bestaudio/best",
                "pr_smart_video_summary": self.tr("回退到通用最高画质"),
                "pr_smart_audio_summary": self.tr("回退到通用最佳音频"),
            }

        video_id = str(video_format.get("format_id") or "")
        video_codec = str(video_format.get("vcodec") or "").upper() or self.tr("未知编码")
        video_quality = str(video_format.get("quality") or self.tr("未知画质"))
        request = {
            "need_video": True,
            "download_mode": "video_audio",
            "selected_video_format_id": video_id,
            "selected_audio_format_id": "",
            "format_selector": video_id,
            "pr_smart_video_summary": f"{video_quality} / {video_codec}",
            "pr_smart_audio_summary": self.tr("使用视频内嵌音频"),
        }

        if video_format.get("has_audio"):
            return request

        if audio_format:
            audio_id = str(audio_format.get("format_id") or "")
            audio_codec = str(audio_format.get("acodec") or "").upper() or self.tr("未知编码")
            audio_quality = str(audio_format.get("quality") or self.tr("未知音频"))
            request.update(
                selected_audio_format_id=audio_id,
                format_selector=f"{video_id}+{audio_id}",
                pr_smart_audio_summary=f"{audio_quality} / {audio_codec}",
            )
            return request

        request.update(
            format_selector="bestvideo+bestaudio/best",
            selected_video_format_id="",
            pr_smart_video_summary=self.tr("回退到通用最高画质"),
            pr_smart_audio_summary=self.tr("回退到通用最佳音频"),
        )
        return request

    def _custom_preference_summary_text(self) -> str:
        codec_text = self.custom_video_codec_combo.currentText() or self.tr("自动")
        container_text = self.custom_container_combo.currentText() or self.tr("自动")
        audio_text = self.custom_audio_codec_combo.currentText() or self.tr("自动")
        return self.tr("自定义偏好：") + f"{codec_text} / {container_text} / {audio_text}"

    def _build_custom_preferences_selector(self) -> str:
        video_codec = self.custom_video_codec_combo.currentData() or "auto"
        container = self.custom_container_combo.currentData() or "auto"
        audio_codec = self.custom_audio_codec_combo.currentData() or "auto"

        video_filters = []
        if video_codec != "auto":
            video_filters.append(f"[vcodec*={video_codec}]")
        if container != "auto":
            video_filters.append(f"[ext={container}]")

        audio_filters = []
        if audio_codec != "auto":
            audio_filters.append(f"[acodec*={audio_codec}]")
        if container == "mp4":
            audio_filters.append("[ext=m4a]")
        elif container == "webm":
            audio_filters.append("[ext=webm]")

        video_expr = "bestvideo" + "".join(video_filters)
        audio_expr = "bestaudio" + "".join(audio_filters)

        selectors = [f"{video_expr}+{audio_expr}"]
        if audio_codec != "auto":
            selectors.append(f"bestvideo{''.join(video_filters)}+bestaudio[acodec*={audio_codec}]")
        if video_codec != "auto":
            selectors.append(f"bestvideo[vcodec*={video_codec}]+bestaudio")
        if container == "mp4":
            selectors.append("bestvideo[ext=mp4]+bestaudio[ext=m4a]")
        elif container == "webm":
            selectors.append("bestvideo[ext=webm]+bestaudio[ext=webm]")
        selectors.append("bestvideo+bestaudio/best")
        return self._combine_selector_chains(selectors)

    def _refresh_selection_summary(self, *_args):
        parts = []
        if self.current_mode_key == "simple":
            parts.append(self.simple_preset_combo.currentText() or self.tr("暂无"))
            if self._is_custom_simple_preset_selected():
                parts.append(self._custom_preference_summary_text())
            elif self._is_pr_smart_preset_selected():
                pr_request = self._build_pr_smart_request() if self.preview_data else {}
                video_summary = pr_request.get("pr_smart_video_summary")
                audio_summary = pr_request.get("pr_smart_audio_summary")
                if video_summary:
                    parts.append(self.tr("视频策略：") + str(video_summary))
                if audio_summary:
                    parts.append(self.tr("音频策略：") + str(audio_summary))
                if self.pr_smart_postprocess_checkbox.isChecked():
                    parts.append(self.tr("AV1->H.265 后处理：开启"))
                if self.pr_smart_transcript_checkbox.isChecked():
                    parts.append(self.tr("视频文稿：开启"))
        else:
            mode_text = self.professional_mode_combo.currentText() or self.tr("暂无模式")
            parts.append(mode_text)
            current_mode = self.professional_mode_combo.currentData() or "video_audio"
            if current_mode in {"video", "video_audio"}:
                parts.append(self.tr("视频流：") + self._describe_stream(self.selected_video_format))
            if current_mode in {"audio", "video_audio"}:
                parts.append(self.tr("音频流：") + self._describe_stream(self.selected_audio_format))

        extras = []
        if self.subtitle_checkbox.isChecked():
            extras.append(self.tr("字幕"))
        if self.thumbnail_checkbox.isChecked():
            extras.append(self.tr("封面"))
        if self.metadata_checkbox.isChecked():
            extras.append(self.tr("元数据"))
        if self.description_txt_checkbox.isChecked():
            extras.append(self.tr("说明TXT"))
        if self._is_pr_smart_preset_selected() and self.pr_smart_transcript_checkbox.isChecked():
            extras.append(self.tr("视频文稿"))
        if extras:
            parts.append(self.tr("附加项：") + self.tr("、").join(extras))

        time_range_summary = self._time_range_summary_text()
        if time_range_summary:
            parts.append(time_range_summary)

        self.last_selection_summary = self.tr("；").join(parts) if parts else self.tr("暂无")
        self.selection_summary_label.setText(self.tr("已选方案：") + self.last_selection_summary)

    def _build_download_request(self) -> dict | None:
        request = {
            "need_video": False,
            "need_subtitle": self.subtitle_checkbox.isChecked(),
            "need_thumbnail": self.thumbnail_checkbox.isChecked(),
            "need_metadata": self.metadata_checkbox.isChecked(),
            "need_description_txt": self.description_txt_checkbox.isChecked(),
            "need_transcript_txt": False,
            "download_mode": "video_audio",
            "selected_video_format_id": "",
            "selected_audio_format_id": "",
            "format_selector": "",
            "enable_time_ranges": False,
            "multi_time_ranges": False,
            "download_sections": [],
            "pr_smart_transcode_hevc_on_av1": False,
        }

        if self.current_mode_key == "simple":
            preset = self.simple_preset_combo.currentData() or "best_quality"
            if preset == "best_quality":
                request.update(need_video=True, download_mode="video_audio", format_selector="bestvideo+bestaudio/best")
            elif preset == "mp4_compatible":
                request.update(need_video=True, download_mode="video_audio", format_selector="bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best")
            elif preset in {"pr_smart", "pr_editing"}:
                request.update(self._build_pr_smart_request())
                request["pr_smart_transcode_hevc_on_av1"] = self.pr_smart_postprocess_checkbox.isChecked()
                request["need_transcript_txt"] = self.pr_smart_transcript_checkbox.isChecked()
                if request["need_transcript_txt"]:
                    request["need_subtitle"] = True
            elif preset == "custom_preferences":
                request.update(need_video=True, download_mode="video_audio", format_selector=self._build_custom_preferences_selector())
            elif preset == "audio_only":
                request.update(need_video=True, download_mode="audio", format_selector="bestaudio/best")
            elif preset == "subtitle_only":
                request["need_subtitle"] = True
            elif preset == "thumbnail_only":
                request["need_thumbnail"] = True
        else:
            mode = self.professional_mode_combo.currentData() or "video_audio"
            request["download_mode"] = mode
            if mode == "audio":
                if not self.selected_audio_format:
                    InfoBar.warning(self.tr("提示"), self.tr("请先选择一个音频流。"), duration=3000, parent=self)
                    return None
                audio_id = self.selected_audio_format.get("format_id") or ""
                request.update(need_video=True, selected_audio_format_id=audio_id, format_selector=audio_id)
            elif mode == "video":
                if not self.selected_video_format:
                    InfoBar.warning(self.tr("提示"), self.tr("请先选择一个视频流。"), duration=3000, parent=self)
                    return None
                video_id = self.selected_video_format.get("format_id") or ""
                request.update(need_video=True, selected_video_format_id=video_id, format_selector=video_id)
            else:
                if not self.selected_video_format:
                    InfoBar.warning(self.tr("提示"), self.tr("请先选择一个视频流。"), duration=3000, parent=self)
                    return None
                video_id = self.selected_video_format.get("format_id") or ""
                if self.selected_video_format.get("has_audio"):
                    request.update(need_video=True, selected_video_format_id=video_id, format_selector=video_id)
                else:
                    if not self.selected_audio_format:
                        InfoBar.warning(self.tr("提示"), self.tr("当前视频流不含音频，请再选择一个音频流。"), duration=3000, parent=self)
                        return None
                    audio_id = self.selected_audio_format.get("format_id") or ""
                    request.update(need_video=True, selected_video_format_id=video_id, selected_audio_format_id=audio_id, format_selector=f"{video_id}+{audio_id}")

        if not any([request["need_video"], request["need_subtitle"], request["need_thumbnail"], request["need_metadata"]]):
            InfoBar.warning(self.tr("提示"), self.tr("请至少选择一项下载内容。"), duration=3000, parent=self)
            return None

        if request["need_subtitle"]:
            subtitle_mode = self._selected_subtitle_mode()
            has_subtitles = self.preview_data.get("has_manual_subtitles") if subtitle_mode == "manual" else self.preview_data.get("has_auto_subtitles")
            if not has_subtitles:
                InfoBar.warning(self.tr("提示"), self.tr("当前资源没有所选字幕来源，将继续执行其余下载项。"), duration=3500, parent=self)

        if self.enable_time_ranges_checkbox.isChecked():
            download_sections = self._collect_download_sections(request["need_video"])
            if download_sections is None:
                return None
            request.update(
                enable_time_ranges=True,
                multi_time_ranges=len(download_sections) > 1,
                download_sections=download_sections,
            )
        return request

    def start_download(self):
        url = self.url_input.text().strip()
        if not self.preview_data or url != self.parsed_url:
            InfoBar.warning(self.tr("提示"), self.tr("请先解析当前链接，再开始下载。"), duration=3000, parent=self)
            return
        request = self._build_download_request()
        if not request:
            return
        self._refresh_edge_cookie_if_needed()
        self.last_result = {}
        self._reset_result_labels()
        self._reset_download_detail_panel()
        self._set_result_actions_enabled(False)
        self._set_controls_enabled(False)
        self._set_download_action_state("downloading")
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr("开始下载…"))
        self.download_thread = VideoDownloadThread(
            url=url,
            work_dir=self._effective_output_dir(),
            need_video=request["need_video"],
            need_subtitle=request["need_subtitle"],
            need_thumbnail=request["need_thumbnail"],
            subtitle_mode=self._selected_subtitle_mode(),
            download_engine_strategy=str(cfg.get(cfg.download_engine_strategy) or "智能选择"),
            download_mode=request["download_mode"],
            selected_video_format_id=request["selected_video_format_id"],
            selected_audio_format_id=request["selected_audio_format_id"],
            format_selector=request["format_selector"],
            need_metadata=request["need_metadata"],
            need_description_txt=request["need_description_txt"],
            need_transcript_txt=request["need_transcript_txt"],
            enable_time_ranges=request["enable_time_ranges"],
            download_sections=request["download_sections"],
            pr_smart_transcode_hevc_on_av1=request["pr_smart_transcode_hevc_on_av1"],
        )
        self.download_thread.progress.connect(self.on_download_progress)
        self.download_thread.progress_detail.connect(self.on_download_progress_detail)
        self.download_thread.detailed_finished.connect(self.on_download_finished)
        self.download_thread.cancelled.connect(self.on_download_cancelled)
        self.download_thread.error.connect(self.on_download_error)
        self.download_thread.start()

    def on_download_progress(self, value: int, status: str):
        self.progress_bar.setValue(value)
        self.status_label.setText(status)

    def on_download_progress_detail(self, detail: dict):
        self._render_download_detail_panel(detail)

    def on_download_finished(self, result: dict):
        self.last_result = result
        self._set_controls_enabled(True)
        self._set_download_action_state("idle")
        self.download_thread = None
        self.progress_bar.setValue(100)
        self.status_label.setText(self.tr("下载完成"))
        self.result_summary.setText(self.tr("方案摘要：") + self.last_selection_summary)
        self.result_work_dir.setText(self.tr("输出目录：") + str(result.get("work_dir") or self.tr("暂无")))
        media_paths = result.get("media_paths") or []
        if len(media_paths) > 1:
            self.result_media.setText(self.tr("主媒体：") + self.tr(f"已下载 {len(media_paths)} 个片段文件，位于 ") + str(result.get("work_dir") or self.tr("暂无")))
        else:
            self.result_media.setText(self.tr("主媒体：") + str(result.get("media_path") or self.tr("未下载")))
        self.result_video.setText(self.tr("视频：") + str(result.get("video_path") or self.tr("未下载或不存在")))
        self.result_audio.setText(self.tr("音频：") + str(result.get("audio_path") or self.tr("未下载或不存在")))
        self.result_subtitle.setText(self.tr("字幕：") + str(result.get("subtitle_path") or self.tr("未下载或不存在")))
        self.result_thumbnail.setText(self.tr("封面：") + str(result.get("thumbnail_path") or self.tr("未下载或不存在")))
        self.result_metadata.setText(self.tr("元数据：") + str(result.get("metadata_path") or self.tr("未下载或不存在")))
        self.result_description_txt.setText(self.tr("说明TXT：") + str(result.get("description_txt_path") or self.tr("未生成或不存在")))
        self.result_transcript_txt.setText(
            self.tr("视频文稿：")
            + str(result.get("transcript_txt_path") or result.get("transcript_message") or self.tr("未生成或不存在"))
        )
        self.result_terms_txt.setText(
            self.tr("AI术语表：")
            + str(result.get("terms_txt_path") or result.get("terms_message") or self.tr("未生成或不存在"))
        )
        transcoded_path = result.get("transcoded_video_path")
        transcoded_codec = result.get("transcoded_video_codec") or self.tr("未触发")
        original_video_path = result.get("original_video_path") or self.tr("未下载或不存在")
        if transcoded_path:
            self.result_transcoded.setText(
                self.tr("H.265后处理：")
                + str(transcoded_path)
                + self.tr("（编码器：")
                + str(transcoded_codec)
                + "）"
            )
            self.result_video.setText(self.tr("视频：") + str(original_video_path))
            self.result_media.setText(self.tr("主媒体：") + str(result.get("media_path") or transcoded_path))
        else:
            postprocess_message = result.get("postprocess_message") or self.tr("未触发")
            self.result_transcoded.setText(self.tr("H.265后处理：") + str(postprocess_message))
        self.result_card.setVisible(True)
        self._adjust_responsive_layout()
        self._set_result_actions_enabled(True, has_video=bool(result.get("video_path")))
        InfoBar.success(self.tr("下载完成"), self.tr("资源已下载完成。"), duration=2500, parent=self)
        send_windows_notification(
            self.tr("下载完成"),
            self.tr("资源已下载完成。"),
            target="download_center",
        )

    def on_download_cancelled(self, message: str):
        self.last_result = {}
        self._reset_result_labels()
        self.result_card.setVisible(False)
        self._adjust_responsive_layout()
        self._set_controls_enabled(True)
        self._set_download_action_state("idle")
        self.download_thread = None
        self._set_result_actions_enabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr("下载已终止"))
        self._reset_download_detail_panel()
        InfoBar.warning(self.tr("下载已终止"), message, duration=4000, parent=self)

    def on_download_error(self, error: str):
        self._set_controls_enabled(True)
        self._set_download_action_state("idle")
        self.download_thread = None
        self._set_result_actions_enabled(bool(self.last_result), bool(self.last_result.get("video_path")))
        self.status_label.setText(self.tr("下载失败"))
        self._reset_download_detail_panel()
        InfoBar.error(self.tr("下载失败"), error, duration=5000, parent=self)

    def open_result_folder(self):
        target_dir = self.last_result.get("work_dir")
        if not target_dir or not Path(target_dir).exists():
            InfoBar.warning(self.tr("提示"), self.tr("当前没有可打开的下载目录。"), duration=3000, parent=self)
            return
        if sys.platform == "win32":
            os.startfile(target_dir)
        elif sys.platform == "darwin":
            subprocess.run(["open", target_dir])
        else:
            subprocess.run(["xdg-open", target_dir])

    def send_download_to_transcription(self):
        video_path = self.last_result.get("video_path")
        if not video_path:
            InfoBar.warning(self.tr("提示"), self.tr("当前结果中没有视频文件，无法送去转录。"), duration=3000, parent=self)
            return
        self.send_to_transcription.emit(video_path)
        InfoBar.success(self.tr("已发送"), self.tr("已将视频发送到语音转录页面。"), duration=2500, parent=self)
