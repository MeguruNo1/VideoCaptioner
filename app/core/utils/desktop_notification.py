from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon

from app.common.signal_bus import signalBus
from app.config import APP_NAME, RESOURCE_PATH
from app.core.utils.logger import setup_logger

logger = setup_logger("desktop_notification")

_tray_icon = None
_last_notification_target = None


def _notification_icon() -> QIcon:
    app = QApplication.instance()
    if app is not None:
        app_icon = app.windowIcon()
        if not app_icon.isNull():
            return app_icon
    return QIcon(str(RESOURCE_PATH / "assets" / "logo.png"))


def _on_message_clicked():
    if _last_notification_target:
        signalBus.notification_clicked.emit(_last_notification_target)


def send_desktop_notification(
    title: str,
    message: str,
    timeout_ms: int = 5000,
    target: str | None = None,
) -> bool:
    app = QApplication.instance()
    if app is None:
        return False

    try:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False

        global _tray_icon, _last_notification_target
        if _tray_icon is None:
            _tray_icon = QSystemTrayIcon(_notification_icon(), app)
            _tray_icon.setToolTip(APP_NAME)
            _tray_icon.messageClicked.connect(_on_message_clicked)

        if not _tray_icon.isVisible():
            _tray_icon.show()

        _last_notification_target = str(target).strip() if target else None
        _tray_icon.showMessage(
            title,
            message,
            QSystemTrayIcon.Information,
            timeout_ms,
        )
        return True
    except Exception as exc:
        logger.warning("发送桌面通知失败: %s", exc)
        return False
