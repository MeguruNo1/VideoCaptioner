from __future__ import annotations

import ctypes
import sys
from datetime import datetime
from pathlib import Path

from yt_dlp.cookies import YoutubeDLCookieJar, extract_cookies_from_browser

from app.config import APPDATA_PATH


COOKIE_FILE_PATH = APPDATA_PATH / "cookies.txt"
YOUTUBE_COOKIE_DOMAINS = ("youtube.com", "youtu.be", "google.com", "googlevideo.com")


class _CookieLogger:
    def debug(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _domain_summary(cookie_jar: YoutubeDLCookieJar) -> tuple[int, bool]:
    domains = {cookie.domain.lstrip(".").lower() for cookie in cookie_jar}
    has_youtube = any(
        any(domain.endswith(target) for target in YOUTUBE_COOKIE_DOMAINS)
        for domain in domains
    )
    return len(cookie_jar), has_youtube


def is_process_elevated() -> bool:
    if sys.platform != "win32":
        return False

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _cookie_result(
    *,
    success: bool,
    status: str,
    message: str,
    path: Path,
    cookie_count: int = 0,
    has_youtube: bool = False,
    updated_at: str = "",
    status_code: str | None = None,
    is_elevated: bool = False,
    needs_elevation_hint: bool = False,
) -> dict:
    return {
        "success": success,
        "status": status,
        "status_code": status_code or status,
        "message": message,
        "path": str(path),
        "cookie_count": cookie_count,
        "has_youtube": has_youtube,
        "updated_at": updated_at,
        "is_elevated": is_elevated,
        "needs_elevation_hint": needs_elevation_hint,
    }


def _describe_export_error(error: Exception) -> tuple[str, str]:
    if isinstance(error, PermissionError):
        return "permission_denied", "Cookie 导出失败：浏览器数据当前不可访问"

    text = str(error).lower()
    if any(token in text for token in ("locked", "in use", "sharing violation")):
        return "browser_locked", "Cookie 导出失败：请关闭 Edge 后重试"
    if any(token in text for token in ("decrypt", "dpapi", "crypt")):
        return "decrypt_failed", "Cookie 导出失败：本机浏览器数据解密失败"
    if "sqlite" in text or "database" in text:
        return "database_error", "Cookie 导出失败：浏览器 Cookie 数据库读取失败"
    return "export_failed", f"Cookie 导出失败：{error}"


def export_edge_cookies(cookie_path: Path | None = None) -> dict:
    target_path = Path(cookie_path or COOKIE_FILE_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    elevated = is_process_elevated()

    try:
        extracted_jar = extract_cookies_from_browser("edge", logger=_CookieLogger())
        export_jar = YoutubeDLCookieJar(str(target_path))
        for cookie in extracted_jar:
            export_jar.set_cookie(cookie)
        export_jar.save(str(target_path), ignore_discard=True, ignore_expires=True)

        cookie_count, has_youtube = _domain_summary(export_jar)
        return _cookie_result(
            success=True,
            status="available" if cookie_count else "empty",
            status_code="export_ok" if cookie_count else "export_empty",
            message="Edge Cookie 导出完成" if cookie_count else "未提取到任何 Cookie",
            path=target_path,
            cookie_count=cookie_count,
            has_youtube=has_youtube,
            updated_at=_now_text(),
            is_elevated=elevated,
            needs_elevation_hint=False,
        )
    except Exception as e:
        status_code, message = _describe_export_error(e)
        return _cookie_result(
            success=False,
            status="failed",
            status_code=status_code,
            message=message,
            path=target_path,
            updated_at=_now_text(),
            is_elevated=elevated,
            needs_elevation_hint=(
                (not elevated)
                and status_code
                in {"permission_denied", "browser_locked", "database_error"}
            ),
        )


def verify_cookie_file(cookie_path: Path | None = None) -> dict:
    target_path = Path(cookie_path or COOKIE_FILE_PATH)
    elevated = is_process_elevated()
    if not target_path.exists():
        return _cookie_result(
            success=False,
            status="missing",
            status_code="file_missing",
            message="cookies.txt 不存在",
            path=target_path,
            is_elevated=elevated,
            needs_elevation_hint=False,
        )

    try:
        cookie_jar = YoutubeDLCookieJar(str(target_path))
        cookie_jar.load(str(target_path), ignore_discard=True, ignore_expires=True)
        cookie_count, has_youtube = _domain_summary(cookie_jar)
        updated_at = datetime.fromtimestamp(target_path.stat().st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        return _cookie_result(
            success=cookie_count > 0,
            status="available" if cookie_count else "empty",
            status_code="verify_ok" if cookie_count else "verify_empty",
            message="Cookie 文件可用" if cookie_count else "Cookie 文件为空",
            path=target_path,
            cookie_count=cookie_count,
            has_youtube=has_youtube,
            updated_at=updated_at,
            is_elevated=elevated,
            needs_elevation_hint=False,
        )
    except Exception as e:
        return _cookie_result(
            success=False,
            status="invalid",
            status_code="verify_invalid",
            message=f"Cookie 文件解析失败：{e}",
            path=target_path,
            is_elevated=elevated,
            needs_elevation_hint=False,
        )
