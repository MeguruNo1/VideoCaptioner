from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from yt_dlp.cookies import YoutubeDLCookieJar, extract_cookies_from_browser

from app.config import APPDATA_PATH, CACHE_PATH, ROOT_PATH

try:
    import rookiepy

    HAS_ROOKIEPY = True
except ImportError:
    rookiepy = None
    HAS_ROOKIEPY = False


COOKIE_FILE_PATH = APPDATA_PATH / "cookies.txt"
PROJECT_ROOT = ROOT_PATH.parent
COOKIE_EXPORT_CACHE_PATH = CACHE_PATH / "cookie_export"
ELEVATED_COOKIE_EXPORT_SCRIPT = ROOT_PATH / "tools" / "elevated_cookie_export.py"
RUNTIME_PYTHON_PATH = PROJECT_ROOT / "runtime" / "python.exe"
UAC_EXPORT_TIMEOUT_MS = 120_000
YOUTUBE_COOKIE_DOMAINS = ("youtube.com", "youtu.be", "google.com", "googlevideo.com")
BILIBILI_COOKIE_DOMAINS = ("bilibili.com",)
BILIBILI_REQUIRED_COOKIES = {
    "SESSDATA",
    "DedeUserID",
    "DedeUserID__ckMd5",
    "bili_jct",
}
EDGE_COOKIE_DOMAINS = (
    ".bilibili.com",
    ".youtube.com",
    ".google.com",
    ".googlevideo.com",
)


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
    has_bilibili: bool = False,
    has_bilibili_login: bool = False,
    bilibili_cookie_names: list[str] | None = None,
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
        "has_bilibili": has_bilibili,
        "has_bilibili_login": has_bilibili_login,
        "bilibili_cookie_names": bilibili_cookie_names or [],
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
    if "appbound" in text or "app-bound" in text:
        return "extract_failed", "Cookie 导出失败：浏览器启用了 App-Bound 加密"
    if any(token in text for token in ("decrypt", "dpapi", "crypt")):
        return "extract_failed", "Cookie 导出失败：本机浏览器数据解密失败"
    if "sqlite" in text or "database" in text:
        return "database_error", "Cookie 导出失败：浏览器 Cookie 数据库读取失败"
    return "extract_failed", f"Cookie 导出失败：{error}"


def _is_app_bound_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        token in text
        for token in (
            "appbound",
            "app-bound",
            "app bound",
            "v130",
            "running as admin",
            "administrator",
        )
    )


def _can_try_uac_export(error: Exception, elevated: bool) -> bool:
    return sys.platform == "win32" and not elevated and _is_app_bound_error(error)


def _normalize_rookie_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": str(cookie.get("domain") or ""),
        "path": str(cookie.get("path") or "/"),
        "secure": bool(cookie.get("secure")),
        "expires": int(cookie.get("expires") or 0),
        "name": str(cookie.get("name") or ""),
        "value": "" if cookie.get("value") is None else str(cookie.get("value")),
        "http_only": bool(cookie.get("http_only")),
    }


def _write_rookie_netscape(cookies: list[dict[str, Any]], target_path: Path) -> None:
    if not rookiepy:
        raise RuntimeError("rookiepy is not available")
    target_path.write_text(rookiepy.to_netscape(cookies), encoding="utf-8")


def _extract_edge_cookies_with_rookiepy() -> list[dict[str, Any]]:
    if not rookiepy:
        raise RuntimeError("rookiepy 未安装")
    cookies = rookiepy.edge(list(EDGE_COOKIE_DOMAINS))
    return [_normalize_rookie_cookie(cookie) for cookie in cookies]


def _extract_edge_cookies_with_ytdlp(target_path: Path) -> YoutubeDLCookieJar:
    extracted_jar = extract_cookies_from_browser("edge", logger=_CookieLogger())
    export_jar = YoutubeDLCookieJar(str(target_path))
    for cookie in extracted_jar:
        export_jar.set_cookie(cookie)
    return export_jar


def _load_cookie_file_summary(cookie_path: Path) -> dict:
    cookie_jar = YoutubeDLCookieJar(str(cookie_path))
    cookie_jar.load(str(cookie_path), ignore_discard=True, ignore_expires=True)
    return _cookie_summary(cookie_jar)


def _python_for_elevated_helper() -> Path:
    return RUNTIME_PYTHON_PATH if RUNTIME_PYTHON_PATH.exists() else Path(sys.executable)


def _uac_result(
    *,
    status_code: str,
    message: str,
    target_path: Path,
    elevated: bool,
    success: bool = False,
    status: str = "failed",
    **summary: Any,
) -> dict:
    return _cookie_result(
        success=success,
        status=status,
        status_code=status_code,
        message=message,
        path=target_path,
        cookie_count=int(summary.get("cookie_count") or 0),
        has_youtube=bool(summary.get("has_youtube") or False),
        has_bilibili=bool(summary.get("has_bilibili") or False),
        has_bilibili_login=bool(summary.get("has_bilibili_login") or False),
        bilibili_cookie_names=list(summary.get("bilibili_cookie_names") or []),
        updated_at=_now_text(),
        is_elevated=elevated,
        needs_elevation_hint=False,
    )


def _finalize_elevated_cookie_export(
    source_path: Path,
    target_path: Path,
    elevated: bool,
    helper_status: dict[str, Any] | None = None,
) -> dict:
    if not source_path.exists():
        return _uac_result(
            status_code="uac_result_invalid",
            message="Cookie 导出失败：提权辅助进程未生成 cookies.txt",
            target_path=target_path,
            elevated=elevated,
        )

    try:
        summary = _load_cookie_file_summary(source_path)
    except Exception as e:
        return _uac_result(
            status_code="uac_result_invalid",
            message=f"Cookie 导出失败：提权辅助进程生成的 cookies.txt 无法解析：{e}",
            target_path=target_path,
            elevated=elevated,
        )

    if summary["cookie_count"] <= 0:
        return _uac_result(
            status_code="browser_cookie_empty",
            message="未能从 Edge 提取到目标站点 Cookie，请确认已登录 B站或 YouTube",
            target_path=target_path,
            elevated=elevated,
            **summary,
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target_path)
    message = "Edge Cookie 导出完成"
    status_code = "export_ok"
    success = True
    status = "available"

    if summary["has_bilibili"] and not summary["has_bilibili_login"]:
        message = "Cookie 导出失败：B站仅检测到访客 Cookie，请确认 Edge 已登录 B站"
        status_code = "bilibili_login_missing"
        success = False
        status = "failed"
    elif helper_status and helper_status.get("message"):
        message = str(helper_status["message"])

    return _uac_result(
        status_code=status_code,
        message=message,
        target_path=target_path,
        elevated=elevated,
        success=success,
        status=status,
        **summary,
    )


def _run_elevated_cookie_export(target_path: Path, elevated: bool) -> dict:
    if not ELEVATED_COOKIE_EXPORT_SCRIPT.exists():
        return _uac_result(
            status_code="uac_helper_missing",
            message="Cookie 导出失败：缺少提权辅助进程",
            target_path=target_path,
            elevated=elevated,
        )

    COOKIE_EXPORT_CACHE_PATH.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    temp_cookie_path = COOKIE_EXPORT_CACHE_PATH / f"cookies-{run_id}.txt"
    status_path = COOKIE_EXPORT_CACHE_PATH / f"cookies-{run_id}.json"
    python_path = _python_for_elevated_helper()
    parameters = subprocess.list2cmdline(
        [str(ELEVATED_COOKIE_EXPORT_SCRIPT), str(temp_cookie_path), str(status_path)]
    )

    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except Exception as e:
        return _uac_result(
            status_code="uac_unavailable",
            message=f"Cookie 导出失败：无法启动提权辅助进程：{e}",
            target_path=target_path,
            elevated=elevated,
        )

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("fMask", ctypes.c_ulong),
            ("hwnd", ctypes.c_void_p),
            ("lpVerb", ctypes.c_wchar_p),
            ("lpFile", ctypes.c_wchar_p),
            ("lpParameters", ctypes.c_wchar_p),
            ("lpDirectory", ctypes.c_wchar_p),
            ("nShow", ctypes.c_int),
            ("hInstApp", ctypes.c_void_p),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", ctypes.c_wchar_p),
            ("hkeyClass", ctypes.c_void_p),
            ("dwHotKey", ctypes.c_ulong),
            ("hIconOrMonitor", ctypes.c_void_p),
            ("hProcess", ctypes.c_void_p),
        ]

    see_mask_nocloseprocess = 0x00000040
    wait_timeout = 0x00000102
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(ShellExecuteInfo)
    info.fMask = see_mask_nocloseprocess
    info.lpVerb = "runas"
    info.lpFile = str(python_path)
    info.lpParameters = parameters
    info.lpDirectory = str(PROJECT_ROOT)
    info.nShow = 0

    launched = shell32.ShellExecuteExW(ctypes.byref(info))
    if not launched:
        error_code = ctypes.get_last_error()
        if error_code == 1223:
            return _uac_result(
                status_code="uac_cancelled",
                message="Cookie 导出已取消：未授予管理员权限",
                target_path=target_path,
                elevated=elevated,
            )
        return _uac_result(
            status_code="uac_launch_failed",
            message=f"Cookie 导出失败：提权辅助进程启动失败（错误码 {error_code}）",
            target_path=target_path,
            elevated=elevated,
        )

    wait_result = kernel32.WaitForSingleObject(info.hProcess, UAC_EXPORT_TIMEOUT_MS)
    kernel32.CloseHandle(info.hProcess)
    if wait_result == wait_timeout:
        return _uac_result(
            status_code="uac_timeout",
            message="Cookie 导出失败：提权辅助进程超时",
            target_path=target_path,
            elevated=elevated,
        )

    try:
        try:
            helper_status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as e:
            return _uac_result(
                status_code="uac_result_invalid",
                message=f"Cookie 导出失败：无法读取提权辅助进程结果：{e}",
                target_path=target_path,
                elevated=elevated,
            )

        if not helper_status.get("success") and not temp_cookie_path.exists():
            return _uac_result(
                status_code=str(helper_status.get("status_code") or "extract_failed"),
                message=str(
                    helper_status.get("message") or "Cookie 导出失败：提权辅助进程执行失败"
                ),
                target_path=target_path,
                elevated=elevated,
            )

        return _finalize_elevated_cookie_export(
            temp_cookie_path,
            target_path,
            elevated,
            helper_status,
        )
    finally:
        for temp_path in (temp_cookie_path, status_path):
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def export_edge_cookies(cookie_path: Path | None = None) -> dict:
    target_path = Path(cookie_path or COOKIE_FILE_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    elevated = is_process_elevated()

    if not HAS_ROOKIEPY:
        return _cookie_result(
            success=False,
            status="failed",
            status_code="rookiepy_missing",
            message="Cookie 导出失败：runtime 缺少 rookiepy",
            path=target_path,
            updated_at=_now_text(),
            is_elevated=elevated,
            needs_elevation_hint=False,
        )

    try:
        cookies = _extract_edge_cookies_with_rookiepy()
        if not cookies:
            return _cookie_result(
                success=False,
                status="empty",
                status_code="browser_cookie_empty",
                message="未能从 Edge 提取到目标站点 Cookie，请确认已登录 B站或 YouTube",
                path=target_path,
                updated_at=_now_text(),
                is_elevated=elevated,
                needs_elevation_hint=False,
            )

        _write_rookie_netscape(cookies, target_path)
        summary = _cookie_summary(cookies)
        message = "Edge Cookie 导出完成"
        status_code = "export_ok"
        success = True
        status = "available"
        if summary["has_bilibili"] and not summary["has_bilibili_login"]:
            message = "Cookie 导出失败：B站仅检测到访客 Cookie，请确认 Edge 已登录 B站"
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
            is_elevated=elevated,
            needs_elevation_hint=False,
        )
    except Exception as e:
        if _can_try_uac_export(e, elevated):
            return _run_elevated_cookie_export(target_path, elevated)

        status_code, message = _describe_export_error(e)
        return _cookie_result(
            success=False,
            status="failed",
            status_code=status_code,
            message=message,
            path=target_path,
            updated_at=_now_text(),
            is_elevated=elevated,
            needs_elevation_hint=False,
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
