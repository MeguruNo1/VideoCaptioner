import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.utils import edge_cookie_utils as cookies


VISITOR_COOKIE = {
    "domain": ".bilibili.com",
    "path": "/",
    "secure": False,
    "expires": 1800000000,
    "name": "buvid3",
    "value": "fake-buvid",
    "http_only": False,
}


LOGIN_COOKIES = [
    VISITOR_COOKIE,
    {
        "domain": ".bilibili.com",
        "path": "/",
        "secure": True,
        "expires": 1800000000,
        "name": "SESSDATA",
        "value": "fake-session",
        "http_only": True,
    },
    {
        "domain": ".bilibili.com",
        "path": "/",
        "secure": False,
        "expires": 1800000000,
        "name": "DedeUserID",
        "value": "123",
        "http_only": False,
    },
    {
        "domain": ".bilibili.com",
        "path": "/",
        "secure": False,
        "expires": 1800000000,
        "name": "DedeUserID__ckMd5",
        "value": "fake-md5",
        "http_only": False,
    },
    {
        "domain": ".bilibili.com",
        "path": "/",
        "secure": False,
        "expires": 1800000000,
        "name": "bili_jct",
        "value": "fake-jct",
        "http_only": False,
    },
]


class EdgeCookieUtilsTests(unittest.TestCase):
    def test_rookie_cookie_writes_netscape_file(self):
        if not cookies.HAS_ROOKIEPY:
            self.skipTest("rookiepy is not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "cookies.txt"
            cookies._write_rookie_netscape([VISITOR_COOKIE], target)
            text = target.read_text(encoding="utf-8")

        self.assertIn("# Netscape HTTP Cookie File", text)
        self.assertIn(".bilibili.com\tTRUE\t/\tFALSE\t1800000000\tbuvid3\tfake-buvid", text)

    def test_bilibili_visitor_cookie_is_not_login(self):
        summary = cookies._cookie_summary([VISITOR_COOKIE])

        self.assertTrue(summary["has_bilibili"])
        self.assertFalse(summary["has_bilibili_login"])
        self.assertEqual(summary["bilibili_cookie_names"], ["buvid3"])

    def test_bilibili_required_cookies_mark_login_available(self):
        summary = cookies._cookie_summary(LOGIN_COOKIES)

        self.assertTrue(summary["has_bilibili"])
        self.assertTrue(summary["has_bilibili_login"])
        self.assertIn("SESSDATA", summary["bilibili_cookie_names"])
        self.assertIn("bili_jct", summary["bilibili_cookie_names"])

    def test_export_reports_rookiepy_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(cookies, "HAS_ROOKIEPY", False):
                result = cookies.export_edge_cookies(Path(temp_dir) / "cookies.txt")

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], "rookiepy_missing")

    def test_export_reports_empty_browser_cookie_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(cookies, "HAS_ROOKIEPY", True), patch.object(
                cookies, "_extract_edge_cookies_with_rookiepy", return_value=[]
            ):
                result = cookies.export_edge_cookies(Path(temp_dir) / "cookies.txt")

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], "browser_cookie_empty")

    def test_export_reports_bilibili_login_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(cookies, "HAS_ROOKIEPY", True), patch.object(
                cookies,
                "_extract_edge_cookies_with_rookiepy",
                return_value=[VISITOR_COOKIE],
            ), patch.object(cookies, "_write_rookie_netscape", return_value=None):
                result = cookies.export_edge_cookies(Path(temp_dir) / "cookies.txt")

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], "bilibili_login_missing")
        self.assertTrue(result["has_bilibili"])
        self.assertFalse(result["has_bilibili_login"])

    def test_export_reports_extract_exception(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(cookies, "HAS_ROOKIEPY", True), patch.object(
                cookies,
                "_extract_edge_cookies_with_rookiepy",
                side_effect=RuntimeError("boom"),
            ):
                result = cookies.export_edge_cookies(Path(temp_dir) / "cookies.txt")

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], "extract_failed")

    def test_export_uses_uac_helper_for_app_bound_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            expected = cookies._cookie_result(
                success=True,
                status="available",
                status_code="export_ok",
                message="Edge Cookie 导出完成",
                path=Path(temp_dir) / "cookies.txt",
                updated_at="2026-05-08 00:00:00",
            )
            with patch.object(cookies, "HAS_ROOKIEPY", True), patch.object(
                cookies, "is_process_elevated", return_value=False
            ), patch.object(
                cookies,
                "_extract_edge_cookies_with_rookiepy",
                side_effect=RuntimeError(
                    "Chrome cookies from version v130 can be decrypted only when running as admin due to appbound encryption"
                ),
            ), patch.object(
                cookies, "_run_elevated_cookie_export", return_value=expected
            ) as uac_export:
                result = cookies.export_edge_cookies(Path(temp_dir) / "cookies.txt")

        self.assertEqual(result["status_code"], "export_ok")
        uac_export.assert_called_once()

    def test_export_does_not_relaunch_uac_when_already_elevated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(cookies, "HAS_ROOKIEPY", True), patch.object(
                cookies, "is_process_elevated", return_value=True
            ), patch.object(
                cookies,
                "_extract_edge_cookies_with_rookiepy",
                side_effect=RuntimeError("app-bound encryption"),
            ), patch.object(cookies, "_run_elevated_cookie_export") as uac_export:
                result = cookies.export_edge_cookies(Path(temp_dir) / "cookies.txt")

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], "extract_failed")
        uac_export.assert_not_called()

    def test_finalize_elevated_cookie_export_copies_valid_cookie_file(self):
        if not cookies.HAS_ROOKIEPY:
            self.skipTest("rookiepy is not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.txt"
            target = Path(temp_dir) / "target.txt"
            cookies._write_rookie_netscape(LOGIN_COOKIES, source)

            result = cookies._finalize_elevated_cookie_export(source, target, False)

            self.assertTrue(result["success"])
            self.assertEqual(result["status_code"], "export_ok")
            self.assertTrue(target.exists())
            self.assertTrue(result["has_bilibili_login"])
            self.assertIn("SESSDATA", result["bilibili_cookie_names"])

    def test_finalize_elevated_cookie_export_keeps_visitor_warning(self):
        if not cookies.HAS_ROOKIEPY:
            self.skipTest("rookiepy is not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.txt"
            target = Path(temp_dir) / "target.txt"
            cookies._write_rookie_netscape([VISITOR_COOKIE], source)

            result = cookies._finalize_elevated_cookie_export(source, target, False)

            self.assertFalse(result["success"])
            self.assertEqual(result["status_code"], "bilibili_login_missing")
            self.assertTrue(target.exists())
            self.assertFalse(result["has_bilibili_login"])


if __name__ == "__main__":
    unittest.main()
