import unittest
from unittest.mock import patch

from app.common.signal_bus import signalBus
from app.core.utils import desktop_notification


class DesktopNotificationTests(unittest.TestCase):
    def setUp(self):
        desktop_notification._reset_notification_state_for_tests()

    def tearDown(self):
        desktop_notification._reset_notification_state_for_tests()

    def test_notification_disabled_skips_all_senders(self):
        with patch.object(desktop_notification.cfg, "get", return_value=False), \
            patch.object(desktop_notification, "_send_macos_native_notification") as native, \
            patch.object(desktop_notification, "_send_qt_tray_notification") as qt:
            result = desktop_notification.send_desktop_notification(
                "title", "message", target="download_center"
            )

        self.assertFalse(result)
        native.assert_not_called()
        qt.assert_not_called()

    def test_macos_native_sender_is_preferred(self):
        with patch.object(desktop_notification.cfg, "get", return_value=True), \
            patch.object(
                desktop_notification,
                "_send_macos_native_notification",
                return_value=True,
            ) as native, \
            patch.object(desktop_notification, "_send_qt_tray_notification") as qt:
            result = desktop_notification.send_desktop_notification(
                "title", "message", target="download_center"
            )

        self.assertTrue(result)
        native.assert_called_once_with("title", "message", 5000, "download_center")
        qt.assert_not_called()

    def test_macos_native_failure_falls_back_to_qt(self):
        with patch.object(desktop_notification.cfg, "get", return_value=True), \
            patch.object(
                desktop_notification,
                "_send_macos_native_notification",
                return_value=False,
            ) as native, \
            patch.object(
                desktop_notification,
                "_send_qt_tray_notification",
                return_value=True,
            ) as qt:
            result = desktop_notification.send_desktop_notification(
                "title", "message", target="subtitle"
            )

        self.assertTrue(result)
        native.assert_called_once_with("title", "message", 5000, "subtitle")
        qt.assert_called_once_with("title", "message", 5000, "subtitle")

    def test_macos_native_exception_falls_back_to_qt(self):
        with patch.object(desktop_notification.cfg, "get", return_value=True), \
            patch.object(
                desktop_notification,
                "_send_macos_native_notification",
                side_effect=RuntimeError("boom"),
            ), \
            patch.object(
                desktop_notification,
                "_send_qt_tray_notification",
                return_value=True,
            ) as qt:
            result = desktop_notification.send_desktop_notification(
                "title", "message", target="transcription"
            )

        self.assertTrue(result)
        qt.assert_called_once_with("title", "message", 5000, "transcription")

    def test_notification_click_emits_target(self):
        received = []

        def collect(target):
            received.append(target)

        signalBus.notification_clicked.connect(collect)
        try:
            desktop_notification._emit_notification_click("download_center")
        finally:
            signalBus.notification_clicked.disconnect(collect)

        self.assertEqual(received, ["download_center"])


if __name__ == "__main__":
    unittest.main()
