from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


EDGE_COOKIE_DOMAINS = (
    ".bilibili.com",
    ".youtube.com",
    ".google.com",
    ".googlevideo.com",
)
YOUTUBE_COOKIE_DOMAINS = ("youtube.com", "youtu.be", "google.com", "googlevideo.com")
BILIBILI_COOKIE_DOMAINS = ("bilibili.com",)
BILIBILI_REQUIRED_COOKIES = {
    "SESSDATA",
    "DedeUserID",
    "DedeUserID__ckMd5",
    "bili_jct",
}


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": str(cookie.get("domain") or ""),
        "path": str(cookie.get("path") or "/"),
        "secure": bool(cookie.get("secure")),
        "expires": int(cookie.get("expires") or 0),
        "name": str(cookie.get("name") or ""),
        "value": "" if cookie.get("value") is None else str(cookie.get("value")),
        "http_only": bool(cookie.get("http_only")),
    }


def _cookie_summary(cookies: Iterable[dict[str, Any]]) -> dict[str, Any]:
    cookie_list = list(cookies)
    domains = {
        str(cookie.get("domain") or "").lstrip(".").lower() for cookie in cookie_list
    }
    bilibili_cookie_names = sorted(
        {
            str(cookie.get("name") or "")
            for cookie in cookie_list
            if any(
                str(cookie.get("domain") or "").lstrip(".").lower().endswith(target)
                for target in BILIBILI_COOKIE_DOMAINS
            )
            and cookie.get("name")
        }
    )
    return {
        "cookie_count": len(cookie_list),
        "has_youtube": any(
            any(domain.endswith(target) for target in YOUTUBE_COOKIE_DOMAINS)
            for domain in domains
        ),
        "has_bilibili": any(
            any(domain.endswith(target) for target in BILIBILI_COOKIE_DOMAINS)
            for domain in domains
        ),
        "has_bilibili_login": BILIBILI_REQUIRED_COOKIES.issubset(
            set(bilibili_cookie_names)
        ),
        "bilibili_cookie_names": bilibili_cookie_names,
    }


def _write_status(status_path: Path, payload: dict[str, Any]) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                **payload,
                "updated_at": _now_text(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _failure(status_path: Path, status_code: str, message: str) -> int:
    _write_status(
        status_path,
        {
            "success": False,
            "status_code": status_code,
            "message": message,
        },
    )
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        return 2

    output_path = Path(argv[1])
    status_path = Path(argv[2])

    try:
        import rookiepy
    except ImportError:
        return _failure(
            status_path,
            "rookiepy_missing",
            "Cookie 导出失败：runtime 缺少 rookiepy",
        )

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_cookies = rookiepy.edge(list(EDGE_COOKIE_DOMAINS))
        cookies = [_normalize_cookie(cookie) for cookie in raw_cookies]
        if not cookies:
            return _failure(
                status_path,
                "browser_cookie_empty",
                "未能从 Edge 提取到目标站点 Cookie，请确认已登录 B站或 YouTube",
            )

        output_path.write_text(rookiepy.to_netscape(cookies), encoding="utf-8")
        summary = _cookie_summary(cookies)
        success = True
        status_code = "export_ok"
        message = "Edge Cookie 导出完成"
        if summary["has_bilibili"] and not summary["has_bilibili_login"]:
            success = False
            status_code = "bilibili_login_missing"
            message = "Cookie 导出失败：B站仅检测到访客 Cookie，请确认 Edge 已登录 B站"

        _write_status(
            status_path,
            {
                "success": success,
                "status_code": status_code,
                "message": message,
                **summary,
            },
        )
        return 0 if success else 1
    except Exception as e:
        return _failure(status_path, "extract_failed", f"Cookie 导出失败：{e}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
