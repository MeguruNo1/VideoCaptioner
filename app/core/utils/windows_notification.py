import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon

from app.config import APP_NAME, RESOURCE_PATH
from app.core.utils.logger import setup_logger

logger = setup_logger("windows_notification")

_tray_icon = None


def _notification_icon() -> QIcon:
    app = QApplication.instance()
    if app is not None:
        app_icon = app.windowIcon()
        if not app_icon.isNull():
            return app_icon
    return QIcon(str(RESOURCE_PATH / "assets" / "logo.png"))


def send_windows_notification(title: str, message: str, timeout_ms: int = 5000) -> bool:
    """Send a Windows desktop notification without blocking task completion."""
    if sys.platform != "win32":
        return False

    app = QApplication.instance()
    if app is None:
        return False

    try:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False

        global _tray_icon
        if _tray_icon is None:
            _tray_icon = QSystemTrayIcon(_notification_icon(), app)
            _tray_icon.setToolTip(APP_NAME)

        if not _tray_icon.isVisible():
            _tray_icon.show()

        _tray_icon.showMessage(
            title,
            message,
            QSystemTrayIcon.Information,
            timeout_ms,
        )
        return True
    except Exception as exc:
        logger.warning("发送 Windows 通知失败: %s", exc)
        return False
