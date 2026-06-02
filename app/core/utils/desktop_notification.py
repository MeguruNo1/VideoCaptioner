from __future__ import annotations

import uuid

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon

from app.common.config import cfg
from app.common.signal_bus import signalBus
from app.config import APP_NAME, RESOURCE_PATH
from app.core.utils.logger import setup_logger

logger = setup_logger("desktop_notification")

_tray_icon = None
_last_notification_target = None
_mac_notification_center = None
_mac_notification_delegate = None
_mac_authorization_requested = False
_mac_authorized = None


def _notification_icon() -> QIcon:
    app = QApplication.instance()
    if app is not None:
        app_icon = app.windowIcon()
        if not app_icon.isNull():
            return app_icon
    return QIcon(str(RESOURCE_PATH / "assets" / "logo.png"))


def _on_message_clicked():
    _emit_notification_click(_last_notification_target)


def _ensure_mac_notification_center():
    global _mac_notification_center, _mac_notification_delegate
    if _mac_notification_center is not None:
        return _mac_notification_center

    try:
        from Foundation import NSObject
        from UserNotifications import UNUserNotificationCenter
    except Exception as exc:
        logger.warning("macOS 原生通知不可用: %s", exc)
        return None

    class MacNotificationDelegate(NSObject):
        def userNotificationCenter_willPresentNotification_withCompletionHandler_(
            self, _center, _notification, completion_handler
        ):
            try:
                from UserNotifications import (
                    UNNotificationPresentationOptionBanner,
                    UNNotificationPresentationOptionList,
                    UNNotificationPresentationOptionSound,
                )

                options = (
                    UNNotificationPresentationOptionBanner
                    | UNNotificationPresentationOptionList
                    | UNNotificationPresentationOptionSound
                )
            except Exception:
                options = 0
            completion_handler(options)

        def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(
            self, _center, response, completion_handler
        ):
            try:
                user_info = (
                    response.notification()
                    .request()
                    .content()
                    .userInfo()
                )
                target = str(user_info.get("target", "") or "").strip()
                _emit_notification_click(target)
            except Exception as exc:
                logger.warning("处理 macOS 通知点击失败: %s", exc)
            finally:
                completion_handler()

    _mac_notification_center = UNUserNotificationCenter.currentNotificationCenter()
    _mac_notification_delegate = MacNotificationDelegate.alloc().init()
    _mac_notification_center.setDelegate_(_mac_notification_delegate)
    return _mac_notification_center


def _request_mac_notification_authorization(center) -> None:
    global _mac_authorization_requested
    if _mac_authorization_requested:
        return

    try:
        from UserNotifications import (
            UNAuthorizationOptionAlert,
            UNAuthorizationOptionSound,
        )

        def _completion(granted, error):
            global _mac_authorized
            _mac_authorized = bool(granted)
            if error:
                logger.warning("macOS 通知授权失败: %s", error)

        _mac_authorization_requested = True
        center.requestAuthorizationWithOptions_completionHandler_(
            UNAuthorizationOptionAlert | UNAuthorizationOptionSound,
            _completion,
        )
    except Exception as exc:
        logger.warning("请求 macOS 通知授权失败: %s", exc)


def _send_macos_native_notification(
    title: str,
    message: str,
    timeout_ms: int = 5000,
    target: str | None = None,
) -> bool:
    del timeout_ms
    center = _ensure_mac_notification_center()
    if center is None:
        return False
    if _mac_authorized is False:
        return False

    try:
        from Foundation import NSDictionary
        from UserNotifications import (
            UNMutableNotificationContent,
            UNNotificationRequest,
        )

        _request_mac_notification_authorization(center)
        content = UNMutableNotificationContent.alloc().init()
        content.setTitle_(str(title or APP_NAME))
        content.setBody_(str(message or ""))
        content.setSound_(None)

        normalized_target = str(target or "").strip()
        if normalized_target:
            content.setUserInfo_(NSDictionary.dictionaryWithDictionary_({
                "target": normalized_target
            }))

        request = UNNotificationRequest.requestWithIdentifier_content_trigger_(
            f"videocaptioner-{uuid.uuid4()}",
            content,
            None,
        )

        def _completion(error):
            if error:
                logger.warning("发送 macOS 原生通知失败: %s", error)

        center.addNotificationRequest_withCompletionHandler_(request, _completion)
        return True
    except Exception as exc:
        logger.warning("发送 macOS 原生通知失败: %s", exc)
        return False


def _send_qt_tray_notification(
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
        logger.warning("发送 Qt 桌面通知失败: %s", exc)
        return False


def send_desktop_notification(
    title: str,
    message: str,
    timeout_ms: int = 5000,
    target: str | None = None,
) -> bool:
    if not bool(cfg.get(cfg.desktop_notifications_enabled)):
        return False

    try:
        if _send_macos_native_notification(title, message, timeout_ms, target):
            return True
        return _send_qt_tray_notification(title, message, timeout_ms, target)
    except Exception as exc:
        logger.warning("发送桌面通知失败: %s", exc)
        return _send_qt_tray_notification(title, message, timeout_ms, target)


def _emit_notification_click(target: str | None) -> None:
    normalized_target = str(target or "").strip()
    if normalized_target:
        signalBus.notification_clicked.emit(normalized_target)


def _reset_notification_state_for_tests() -> None:
    global _tray_icon, _last_notification_target
    global _mac_notification_center, _mac_notification_delegate
    global _mac_authorization_requested, _mac_authorized
    _tray_icon = None
    _last_notification_target = None
    _mac_notification_center = None
    _mac_notification_delegate = None
    _mac_authorization_requested = False
    _mac_authorized = None
