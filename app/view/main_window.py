import os
from pathlib import Path

import psutil
from PyQt5.QtCore import QEvent, QRect, Qt, QSize, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import QApplication
from qframelesswindow.utils import startSystemMove
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (
    FluentWindow,
    InfoBar,
    MessageBox,
    NavigationItemPosition,
    SplashScreen,
    isDarkTheme,
)

from app.common.config import cfg
from app.common.signal_bus import signalBus
from app.config import ASSETS_PATH, GITHUB_REPO_URL
from app.view.download_center_interface import DownloadCenterInterface
from app.view.home_interface import HomeInterface
from app.view.setting_interface import SettingInterface

LOGO_PATH = ASSETS_PATH / "logo.png"
MAC_TRAFFIC_LIGHT_ROW_HEIGHT = 32
MAC_TITLE_BAR_HEIGHT = 48
MAC_CHROME_LEFT_PADDING = 14
MAC_TRAFFIC_LIGHT_BUTTON_AREA_WIDTH = 96


class MainWindow(FluentWindow):

    def __init__(self):
        super().__init__()
        self._mac_drag_widgets = ()
        self._hideNavigationReturnButton()
        self._styleMacTitleBarBrand()
        self._installMacDragEventFilters()
        self.navigationInterface.displayModeChanged.connect(
            self._reserveMacTitleBarSpaceForNavigation
        )
        self.navigationInterface.panel.expandAni.finished.connect(
            self._reserveMacTitleBarSpaceForNavigation
        )
        cfg.themeMode.valueChanged.connect(lambda *_: self._applyMacWindowChromeStyle())
        self.navigationInterface.installEventFilter(self)
        self.initWindow()

        # 创建子界面
        self.homeInterface = HomeInterface(self)
        self.settingInterface = SettingInterface(self)
        self.downloadCenterInterface = DownloadCenterInterface(self)
        self.downloadCenterInterface.send_to_transcription.connect(
            self.open_downloaded_video_in_transcription
        )
        signalBus.notification_clicked.connect(self.on_notification_clicked)

        # 初始化导航界面
        self.initNavigation()
        self.splashScreen.finish()

        # 注册退出处理， 清理进程
        import atexit

        atexit.register(self.stop)

    def initNavigation(self):
        """初始化导航栏"""
        # 添加导航项
        self.addSubInterface(self.homeInterface, FIF.HOME, self.tr("主页"))
        self.addSubInterface(
            self.downloadCenterInterface, FIF.DOWNLOAD, self.tr("下载中心")
        )

        self.navigationInterface.addSeparator()

        # 在底部添加自定义小部件
        self.navigationInterface.addItem(
            routeKey="avatar",
            text="GitHub",
            icon=FIF.GITHUB,
            onClick=self.onGithubDialog,
            position=NavigationItemPosition.BOTTOM,
        )
        self.addSubInterface(
            self.settingInterface,
            FIF.SETTING,
            self.tr("Settings"),
            NavigationItemPosition.BOTTOM,
        )

        # 设置默认界面
        self.switchTo(self.homeInterface)

    def switchTo(self, interface):
        if interface.windowTitle():
            self.setWindowTitle(interface.windowTitle())
        else:
            self.setWindowTitle(self.tr("卡卡字幕助手 -- VideoCaptioner"))
        self.stackedWidget.setCurrentWidget(interface, popOut=False)

    def systemTitleBarRect(self, size: QSize) -> QRect:
        """Place native macOS traffic-light buttons on the left."""
        return QRect(0, 0 if self.isFullScreen() else 8, 75, size.height())

    def _macTrafficLightRowHeight(self) -> int:
        if self.isFullScreen():
            return 0
        return MAC_TRAFFIC_LIGHT_ROW_HEIGHT

    def _macContentTopMargin(self) -> int:
        title_bar_height = self.titleBar.height() or MAC_TITLE_BAR_HEIGHT
        return self._macTrafficLightRowHeight() + title_bar_height

    def _hideNavigationReturnButton(self):
        """This branch uses no navigation back button in the window chrome."""
        if not hasattr(self.navigationInterface, "panel"):
            return

        self.navigationInterface.panel.setReturnButtonVisible(False)
        self.navigationInterface.panel.returnButton.setDisabled(True)

    def _styleMacTitleBarBrand(self):
        """Align title-bar branding with the compact navigation icon column."""
        if hasattr(self.titleBar, "hBoxLayout"):
            self.titleBar.hBoxLayout.setContentsMargins(
                MAC_CHROME_LEFT_PADDING, 0, 0, 0
            )
            self.titleBar.hBoxLayout.setSpacing(8)

        if hasattr(self.titleBar, "titleLabel"):
            self.titleBar.titleLabel.setStyleSheet(
                "font-size: 16px; font-weight: 600;"
            )

    def _installMacDragEventFilters(self):
        widgets = [
            self.titleBar,
            self.navigationInterface,
            self.navigationInterface.panel,
        ]
        for attr_name in ("iconLabel", "titleLabel"):
            widget = getattr(self.titleBar, attr_name, None)
            if widget is not None:
                widgets.append(widget)

        scroll_widget = getattr(self.navigationInterface.panel, "scrollWidget", None)
        if scroll_widget is not None:
            widgets.append(scroll_widget)

        self._mac_drag_widgets = tuple(widgets)
        for widget in self._mac_drag_widgets:
            widget.installEventFilter(self)

    def _reserveMacTitleBarSpace(self):
        """Reserve a dedicated macOS traffic-light row above app chrome."""
        traffic_light_row_height = self._macTrafficLightRowHeight()
        self.titleBar.move(0, traffic_light_row_height)

        content_top_margin = self._macContentTopMargin()
        self.widgetLayout.setContentsMargins(0, content_top_margin, 0, 0)

        panel = self.navigationInterface.panel
        available_height = max(0, self.height() - content_top_margin)
        panel.move(0, content_top_margin)
        panel.setFixedHeight(available_height)

    def _reserveMacTitleBarSpaceForNavigation(self):
        """Prevent navigation from occupying the native macOS title bar area."""
        self._reserveMacTitleBarSpace()

    def _applyMacWindowChromeStyle(self):
        """Use Qt translucent chrome without covering the main content."""
        panel = self.navigationInterface.panel
        panel.scrollArea.setObjectName("macNavigationScrollArea")
        panel.scrollArea.viewport().setObjectName("macNavigationScrollViewport")
        panel.scrollWidget.setObjectName("macNavigationScrollWidget")
        panel.scrollArea.setAttribute(Qt.WA_TranslucentBackground, True)
        panel.scrollArea.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        panel.scrollWidget.setAttribute(Qt.WA_TranslucentBackground, True)

        if isDarkTheme():
            styles = {
                "macTitleBarChrome": (
                    "background: rgba(26, 27, 30, 0.84);"
                    "border-bottom: 1px solid rgba(255, 255, 255, 0.08);"
                ),
                "macNavigationChrome": (
                    "background: rgba(24, 25, 28, 0.86);"
                    "border-right: 1px solid rgba(255, 255, 255, 0.08);"
                ),
                "macNavigationPanelChrome": (
                    "background: transparent;"
                    "border: none;"
                ),
            }
        else:
            styles = {
                "macTitleBarChrome": (
                    "background: rgba(255, 255, 255, 0.88);"
                    "border-bottom: 1px solid rgba(17, 24, 39, 0.10);"
                ),
                "macNavigationChrome": (
                    "background: rgba(250, 251, 253, 0.94);"
                    "border-right: 1px solid rgba(17, 24, 39, 0.12);"
                ),
                "macNavigationPanelChrome": (
                    "background: transparent;"
                    "border: none;"
                ),
            }

        chrome_widgets = {
            "macTitleBarChrome": self.titleBar,
            "macNavigationChrome": self.navigationInterface,
            "macNavigationPanelChrome": panel,
        }
        for object_name, widget in chrome_widgets.items():
            widget.setObjectName(object_name)
            widget.setAttribute(Qt.WA_TranslucentBackground, True)
            widget.setStyleSheet(
                f"QWidget#{object_name} {{ {styles[object_name]} }}"
            )

        navigation_inner_style = """
            QScrollArea#macNavigationScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#macNavigationScrollViewport {
                background: transparent;
                border: none;
            }
            QWidget#macNavigationScrollWidget {
                background: transparent;
                border: none;
            }
        """
        panel.scrollArea.setStyleSheet(navigation_inner_style)
        panel.scrollArea.viewport().setStyleSheet(navigation_inner_style)
        panel.scrollWidget.setStyleSheet(navigation_inner_style)

    def _isMacTrafficLightRowDragPoint(self, pos) -> bool:
        return (
            not self.isFullScreen()
            and pos.y() < self._macTrafficLightRowHeight()
            and pos.x() > MAC_TRAFFIC_LIGHT_BUTTON_AREA_WIDTH
        )

    def _startMacWindowDrag(self, global_pos):
        if self.isFullScreen():
            return False

        startSystemMove(self, global_pos)
        return True

    def initWindow(self):
        """初始化窗口"""
        self.resize(1200, 800)
        self.setMinimumWidth(700)
        self.setWindowIcon(QIcon(str(LOGO_PATH)))
        self.setWindowTitle(self.tr("卡卡字幕助手 -- VideoCaptioner"))

        # 创建启动画面
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        # 设置窗口位置, 居中
        desktop = QApplication.desktop().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

        self.show()
        self._applyMacWindowChromeStyle()
        QApplication.processEvents()

    def onGithubDialog(self):
        """打开GitHub"""
        w = MessageBox(
            self.tr("GitHub信息"),
            self.tr(
                "VideoCaptioner 由本人在课余时间独立开发完成，目前托管在GitHub上，欢迎Star和Fork。项目诚然还有很多地方需要完善，遇到软件的问题或者BUG欢迎提交Issue。\n\n https://github.com/WEIFENG2333/VideoCaptioner"
            ),
            self,
        )
        w.yesButton.setText(self.tr("打开 GitHub"))
        w.cancelButton.hide()
        if w.exec():
            QDesktopServices.openUrl(QUrl(GITHUB_REPO_URL))

    def open_downloaded_video_in_transcription(self, file_path: str):
        try:
            normalized_path = str(Path(file_path).expanduser())
            if not normalized_path or not Path(normalized_path).exists():
                raise FileNotFoundError(f"下载结果不存在: {file_path}")
            self.switchTo(self.homeInterface)
            self.homeInterface.open_transcription(
                normalized_path, need_next_task=False
            )
        except Exception as exc:
            InfoBar.error(
                self.tr("打开转录失败"),
                str(exc),
                duration=4000,
                parent=self,
            )

    def on_notification_clicked(self, target: str):
        target = str(target or "").strip()
        if target == "download_center":
            self.switchTo(self.downloadCenterInterface)
        elif target == "transcription":
            self.switchTo(self.homeInterface)
            self.homeInterface.show_transcription_page()
        elif target == "subtitle":
            self.switchTo(self.homeInterface)
            self.homeInterface.show_subtitle_optimization_page()
        else:
            return
        self._activate_from_notification()

    def _activate_from_notification(self):
        if self.windowState() & Qt.WindowMinimized:
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reserveMacTitleBarSpaceForNavigation()
        if hasattr(self, "splashScreen"):
            self.splashScreen.resize(self.size())

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and self._isMacTrafficLightRowDragPoint(event.pos())
            and self._startMacWindowDrag(event.globalPos())
        ):
            event.accept()
            return

        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.MouseButtonPress
            and event.button() == Qt.LeftButton
            and obj in getattr(self, "_mac_drag_widgets", ())
        ):
            if obj is self.titleBar and hasattr(self.titleBar, "canDrag"):
                if not self.titleBar.canDrag(event.pos()):
                    return super().eventFilter(obj, event)

            if self._startMacWindowDrag(event.globalPos()):
                event.accept()
                return True

        navigation_interface = getattr(self, "navigationInterface", None)
        if obj is navigation_interface and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._reserveMacTitleBarSpaceForNavigation)
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        # 关闭所有子界面
        # self.homeInterface.close()
        # self.settingInterface.close()
        super().closeEvent(event)

        # 强制退出应用程序
        QApplication.quit()

        # 确保所有线程和进程都被终止 要是一些错误退出就不会处理了。
        # import os
        # os._exit(0)

    def stop(self):
        # 找到 FFmpeg 进程并关闭
        process = psutil.Process(os.getpid())
        for child in process.children(recursive=True):
            child.kill()
