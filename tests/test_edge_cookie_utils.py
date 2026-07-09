import os
import stat
import unittest
import tempfile
from http.cookiejar import Cookie
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

YOUTUBE_COOKIE = {
    "domain": ".youtube.com",
    "path": "/",
    "secure": True,
    "expires": 1800000000,
    "name": "VISITOR_INFO1_LIVE",
    "value": "fake-visitor",
    "http_only": False,
}


UNRELATED_COOKIE = {
    "domain": ".example.com",
    "path": "/",
    "secure": True,
    "expires": 1800000000,
    "name": "UNRELATED_SESSION",
    "value": "fake-unrelated",
    "http_only": True,
}


EVIL_GOOGLE_SUFFIX_COOKIE = {
    "domain": ".evilgoogle.com",
    "path": "/",
    "secure": True,
    "expires": 1800000000,
    "name": "EVIL_GOOGLE_SESSION",
    "value": "fake-evil",
    "http_only": True,
}


class EdgeCookieUtilsTests(unittest.TestCase):
    @staticmethod
    def _cookie_from_dict(data: dict) -> Cookie:
        return Cookie(
            version=0,
            name=data["name"],
            value=data["value"],
            port=None,
            port_specified=False,
            domain=data["domain"],
            domain_specified=True,
            domain_initial_dot=data["domain"].startswith("."),
            path=data["path"],
            path_specified=True,
            secure=data["secure"],
            expires=data["expires"],
            discard=False,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": data["http_only"]},
            rfc2109=False,
        )

    @staticmethod
    def _cookie_file_line(data: dict) -> str:
        return "\t".join(
            [
                data["domain"],
                "TRUE" if data["domain"].startswith(".") else "FALSE",
                data["path"],
                "TRUE" if data["secure"] else "FALSE",
                str(data["expires"]),
                data["name"],
                data["value"],
            ]
        )

    @classmethod
    def _cookie_jar(cls, target: Path, cookie_dicts: list[dict]):
        jar = cookies.YoutubeDLCookieJar(str(target))
        for cookie in cookie_dicts:
            jar.set_cookie(cls._cookie_from_dict(cookie))
        return jar

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

    def test_cookie_summary_does_not_match_lookalike_suffix_domain(self):
        summary = cookies._cookie_summary([EVIL_GOOGLE_SUFFIX_COOKIE])

        self.assertFalse(summary["has_youtube"])
        self.assertFalse(summary["has_bilibili"])

    def test_export_reports_rookiepy_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                cookies,
                "_extract_browser_cookies_with_ytdlp",
                side_effect=RuntimeError("missing browser cookies"),
            ):
                result = cookies.export_browser_cookies(Path(temp_dir) / "cookies.txt")

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], "extract_failed")

    def test_export_reports_empty_browser_cookie_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "cookies.txt"
            with patch.object(
                cookies,
                "_extract_browser_cookies_with_ytdlp",
                return_value=self._cookie_jar(target, []),
            ):
                result = cookies.export_browser_cookies(target)

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], "browser_cookie_empty")

    def test_export_reports_bilibili_login_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "cookies.txt"
            with patch.object(
                cookies,
                "_extract_browser_cookies_with_ytdlp",
                return_value=self._cookie_jar(target, [VISITOR_COOKIE]),
            ):
                result = cookies.export_browser_cookies(target)

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], "bilibili_login_missing")
        self.assertTrue(result["has_bilibili"])
        self.assertFalse(result["has_bilibili_login"])

    def test_export_reports_extract_exception(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                cookies,
                "_extract_browser_cookies_with_ytdlp",
                side_effect=RuntimeError("boom"),
            ):
                result = cookies.export_browser_cookies(Path(temp_dir) / "cookies.txt")

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], "extract_failed")

    def test_export_writes_valid_cookie_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "cookies.txt"
            with patch.object(
                cookies,
                "_extract_browser_cookies_with_ytdlp",
                return_value=self._cookie_jar(target, LOGIN_COOKIES),
            ):
                result = cookies.export_browser_cookies(target)

            verified = cookies.verify_cookie_file(target)

            self.assertTrue(result["success"])
            self.assertEqual(result["status_code"], "export_ok")
            self.assertTrue(target.exists())
            self.assertTrue(verified["has_bilibili_login"])
            if os.name == "posix":
                self.assertEqual(
                    stat.S_IMODE(target.stat().st_mode), cookies.PRIVATE_FILE_MODE
                )

    def test_export_writes_only_supported_download_cookie_domains(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "cookies.txt"
            with patch.object(
                cookies,
                "_extract_browser_cookies_with_ytdlp",
                return_value=self._cookie_jar(
                    target,
                    [YOUTUBE_COOKIE, UNRELATED_COOKIE, EVIL_GOOGLE_SUFFIX_COOKIE],
                ),
            ):
                result = cookies.export_browser_cookies(target)

            file_text = target.read_text(encoding="utf-8")
            verified = cookies.verify_cookie_file(target)

            self.assertTrue(result["success"])
            self.assertEqual(result["cookie_count"], 1)
            self.assertEqual(verified["cookie_count"], 1)
            self.assertIn("VISITOR_INFO1_LIVE", file_text)
            self.assertNotIn("UNRELATED_SESSION", file_text)
            self.assertNotIn("EVIL_GOOGLE_SESSION", file_text)

    def test_verify_hardens_existing_cookie_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "cookies.txt"
            target.write_text(
                "\n".join(
                    [
                        "# Netscape HTTP Cookie File",
                        "# Source browser: Safari",
                        self._cookie_file_line(YOUTUBE_COOKIE),
                        self._cookie_file_line(UNRELATED_COOKIE),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            if os.name == "posix":
                Path(temp_dir).chmod(0o755)
                target.chmod(0o644)

            result = cookies.verify_cookie_file(target)
            file_text = target.read_text(encoding="utf-8")

            self.assertTrue(result["success"])
            self.assertEqual(result["cookie_count"], 1)
            self.assertIn("VISITOR_INFO1_LIVE", file_text)
            self.assertNotIn("UNRELATED_SESSION", file_text)
            if os.name == "posix":
                self.assertEqual(
                    stat.S_IMODE(Path(temp_dir).stat().st_mode),
                    cookies.PRIVATE_DIR_MODE,
                )
                self.assertEqual(
                    stat.S_IMODE(target.stat().st_mode), cookies.PRIVATE_FILE_MODE
                )

    def test_export_defaults_to_safari_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "cookies.txt"
            with patch.object(
                cookies,
                "_extract_browser_cookies_with_ytdlp",
                return_value=self._cookie_jar(target, [YOUTUBE_COOKIE]),
            ) as extract:
                result = cookies.export_browser_cookies(target)

            extract.assert_called_once_with(target, "safari")
            self.assertTrue(result["success"])
            self.assertEqual(result["source_browser"], "safari")
            self.assertEqual(result["source_browser_label"], "Safari")
            self.assertIn("# Source browser: Safari", target.read_text())

    def test_export_uses_selected_browser_without_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "cookies.txt"
            with patch.object(
                cookies,
                "_extract_browser_cookies_with_ytdlp",
                return_value=self._cookie_jar(target, [YOUTUBE_COOKIE]),
            ) as extract:
                result = cookies.export_browser_cookies(target, "Chrome")

            extract.assert_called_once_with(target, "chrome")
            self.assertTrue(result["success"])
            self.assertEqual(result["source_browser"], "chrome")
            self.assertEqual(result["source_browser_label"], "Chrome")


if __name__ == "__main__":
    unittest.main()
