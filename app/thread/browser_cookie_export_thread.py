from PyQt5.QtCore import QThread, pyqtSignal


class BrowserCookieExportThread(QThread):
    completed = pyqtSignal(dict)

    def __init__(self, browser: str, parent=None):
        super().__init__(parent)
        self.browser = browser

    def run(self):
        try:
            from app.core.utils.edge_cookie_utils import export_browser_cookies

            result = export_browser_cookies(browser=self.browser)
        except Exception as exc:
            result = {
                "success": False,
                "status": "failed",
                "status_code": "startup_export_failed",
                "message": f"浏览器 Cookie 自动提取失败：{exc}",
                "source_browser": self.browser,
                "source_browser_label": self.browser,
            }

        self.completed.emit(result)
