from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from yt_dlp.cookies import YoutubeDLCookieJar, extract_cookies_from_browser

from app.config import APPDATA_PATH

COOKIE_FILE_PATH = APPDATA_PATH / "cookies.txt"
COOKIE_BROWSER_LABELS = {
    "safari": "Safari",
    "chrome": "Chrome",
    "edge": "Edge",
}
DEFAULT_COOKIE_BROWSER = "safari"
YOUTUBE_COOKIE_DOMAINS = ("youtube.com", "youtu.be", "google.com", "googlevideo.com")
BILIBILI_COOKIE_DOMAINS = ("bilibili.com",)
BILIBILI_REQUIRED_COOKIES = {
    "SESSDATA",
    "DedeUserID",
    "DedeUserID__ckMd5",
    "bili_jct",
}


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


def normalize_cookie_browser(browser: str | None) -> str:
    value = str(browser or "").strip().lower()
    if value in COOKIE_BROWSER_LABELS:
        return value
    return DEFAULT_COOKIE_BROWSER


def cookie_browser_label(browser: str | None) -> str:
    if not str(browser or "").strip():
        return "未知"
    return COOKIE_BROWSER_LABELS[normalize_cookie_browser(browser)]


def _cookie_attr(cookie: Any, name: str, default: Any = None) -> Any:
    if isinstance(cookie, dict):
        return cookie.get(name, default)
    return getattr(cookie, name, default)


def _cookie_domain(cookie: Any) -> str:
    return str(_cookie_attr(cookie, "domain", "") or "").lstrip(".").lower()


def _cookie_name(cookie: Any) -> str:
    return str(_cookie_attr(cookie, "name", "") or "")


def _cookie_summary(cookies: Iterable[Any]) -> dict:
    cookie_list = list(cookies)
    domains = {_cookie_domain(cookie) for cookie in cookie_list}
    names_by_domain = [
        _cookie_name(cookie)
        for cookie in cookie_list
        if any(_cookie_domain(cookie).endswith(target) for target in BILIBILI_COOKIE_DOMAINS)
    ]
    bilibili_cookie_names = sorted({name for name in names_by_domain if name})
    has_youtube = any(
        any(domain.endswith(target) for target in YOUTUBE_COOKIE_DOMAINS)
        for domain in domains
    )
    has_bilibili = any(
        any(domain.endswith(target) for target in BILIBILI_COOKIE_DOMAINS)
        for domain in domains
    )
    has_bilibili_login = BILIBILI_REQUIRED_COOKIES.issubset(
        set(bilibili_cookie_names)
    )
    return {
        "cookie_count": len(cookie_list),
        "has_youtube": has_youtube,
        "has_bilibili": has_bilibili,
        "has_bilibili_login": has_bilibili_login,
        "bilibili_cookie_names": bilibili_cookie_names,
    }


def _cookie_result(
    *,
    success: bool,
    status: str,
    message: str,
    path: Path,
    cookie_count: int = 0,
    has_youtube: bool = False,
    has_bilibili: bool = False,
    has_bilibili_login: bool = False,
    bilibili_cookie_names: list[str] | None = None,
    updated_at: str = "",
    status_code: str | None = None,
    source_browser: str | None = None,
    is_elevated: bool = False,
    needs_elevation_hint: bool = False,
) -> dict:
    normalized_browser = (
        normalize_cookie_browser(source_browser) if str(source_browser or "").strip() else ""
    )
    return {
        "success": success,
        "status": status,
        "status_code": status_code or status,
        "message": message,
        "path": str(path),
        "cookie_count": cookie_count,
        "has_youtube": has_youtube,
        "has_bilibili": has_bilibili,
        "has_bilibili_login": has_bilibili_login,
        "bilibili_cookie_names": bilibili_cookie_names or [],
        "updated_at": updated_at,
        "source_browser": normalized_browser,
        "source_browser_label": cookie_browser_label(normalized_browser),
        "is_elevated": is_elevated,
        "needs_elevation_hint": needs_elevation_hint,
    }


def _describe_export_error(
    error: Exception, browser: str | None = None
) -> tuple[str, str]:
    label = cookie_browser_label(browser)
    if isinstance(error, PermissionError):
        return "permission_denied", f"{label} Cookie 导出失败：浏览器数据当前不可访问"

    text = str(error).lower()
    if any(token in text for token in ("locked", "in use", "sharing violation")):
        return "browser_locked", f"{label} Cookie 导出失败：请关闭 {label} 后重试"
    if any(token in text for token in ("decrypt", "crypt", "keychain")):
        return "extract_failed", f"{label} Cookie 导出失败：本机浏览器数据解密失败"
    if "sqlite" in text or "database" in text:
        return "database_error", f"{label} Cookie 导出失败：浏览器 Cookie 数据库读取失败"
    return "extract_failed", f"{label} Cookie 导出失败：{error}"


def _extract_browser_cookies_with_ytdlp(
    target_path: Path, browser: str | None = None
) -> YoutubeDLCookieJar:
    browser = normalize_cookie_browser(browser)
    extracted_jar = extract_cookies_from_browser(browser, logger=_CookieLogger())
    export_jar = YoutubeDLCookieJar(str(target_path))
    for cookie in extracted_jar:
        export_jar.set_cookie(cookie)
    return export_jar


def _write_cookie_jar(
    cookie_jar: YoutubeDLCookieJar, target_path: Path, browser: str | None = None
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Netscape HTTP Cookie File",
        "# This file is generated by VideoCaptioner.",
        f"# Source browser: {cookie_browser_label(browser)}",
    ]
    for cookie in cookie_jar:
        domain = str(cookie.domain or "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = str(cookie.path or "/")
        secure = "TRUE" if bool(cookie.secure) else "FALSE"
        expires = str(int(cookie.expires or 0))
        name = str(cookie.name or "")
        value = str(cookie.value or "")
        lines.append(
            "\t".join([domain, include_subdomains, path, secure, expires, name, value])
        )
    target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_cookie_source_browser(target_path: Path) -> str | None:
    try:
        for line in target_path.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines():
            if line.startswith("# Source browser:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def export_browser_cookies(
    cookie_path: Path | None = None, browser: str | None = None
) -> dict:
    target_path = Path(cookie_path or COOKIE_FILE_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    browser = normalize_cookie_browser(browser)
    browser_label = cookie_browser_label(browser)

    try:
        cookie_jar = _extract_browser_cookies_with_ytdlp(target_path, browser)
        cookies = list(cookie_jar)
        if not cookies:
            return _cookie_result(
                success=False,
                status="empty",
                status_code="browser_cookie_empty",
                message=(
                    f"未能从 {browser_label} 提取到目标站点 Cookie，"
                    "请确认该浏览器已登录 B站或 YouTube"
                ),
                path=target_path,
                updated_at=_now_text(),
                source_browser=browser,
            )

        _write_cookie_jar(cookie_jar, target_path, browser)
        summary = _cookie_summary(cookies)
        message = f"{browser_label} Cookie 导出完成"
        status_code = "export_ok"
        success = True
        status = "available"
        if summary["has_bilibili"] and not summary["has_bilibili_login"]:
            message = (
                f"{browser_label} Cookie 导出失败：B站仅检测到访客 Cookie，"
                "请确认该浏览器已登录 B站"
            )
            status_code = "bilibili_login_missing"
            success = False
            status = "failed"
        return _cookie_result(
            success=success,
            status=status,
            status_code=status_code,
            message=message,
            path=target_path,
            cookie_count=summary["cookie_count"],
            has_youtube=summary["has_youtube"],
            has_bilibili=summary["has_bilibili"],
            has_bilibili_login=summary["has_bilibili_login"],
            bilibili_cookie_names=summary["bilibili_cookie_names"],
            updated_at=_now_text(),
            source_browser=browser,
        )
    except Exception as exc:
        status_code, message = _describe_export_error(exc, browser)
        return _cookie_result(
            success=False,
            status="failed",
            status_code=status_code,
            message=message,
            path=target_path,
            updated_at=_now_text(),
            source_browser=browser,
        )


def export_edge_cookies(cookie_path: Path | None = None) -> dict:
    return export_browser_cookies(cookie_path, "Edge")


def verify_cookie_file(cookie_path: Path | None = None) -> dict:
    target_path = Path(cookie_path or COOKIE_FILE_PATH)
    source_browser = (
        _read_cookie_source_browser(target_path) if target_path.exists() else None
    )
    if not target_path.exists():
        return _cookie_result(
            success=False,
            status="missing",
            status_code="file_missing",
            message="cookies.txt 不存在",
            path=target_path,
            source_browser=source_browser,
        )

    try:
        cookie_jar = YoutubeDLCookieJar(str(target_path))
        cookie_jar.load(str(target_path), ignore_discard=True, ignore_expires=True)
        summary = _cookie_summary(cookie_jar)
        updated_at = datetime.fromtimestamp(target_path.stat().st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        return _cookie_result(
            success=summary["cookie_count"] > 0,
            status="available" if summary["cookie_count"] else "empty",
            status_code="verify_ok" if summary["cookie_count"] else "verify_empty",
            message="Cookie 文件可用" if summary["cookie_count"] else "Cookie 文件为空",
            path=target_path,
            cookie_count=summary["cookie_count"],
            has_youtube=summary["has_youtube"],
            has_bilibili=summary["has_bilibili"],
            has_bilibili_login=summary["has_bilibili_login"],
            bilibili_cookie_names=summary["bilibili_cookie_names"],
            updated_at=updated_at,
            source_browser=source_browser,
        )
    except Exception as exc:
        return _cookie_result(
            success=False,
            status="invalid",
            status_code="verify_invalid",
            message=f"Cookie 文件解析失败：{exc}",
            path=target_path,
            source_browser=source_browser,
        )
