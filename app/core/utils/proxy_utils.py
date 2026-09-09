import os
import socket
from typing import Mapping



PROXY_MODE_AUTO = "自动检测"
PROXY_MODE_MANUAL = "手动设置"
PROXY_MODE_OFF = "不使用代理"

PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)

COMMON_LOCAL_PROXY_PORTS = (7897, 7890, 10809, 10808, 7891)


def normalize_proxy_url(proxy_url: str | None) -> str:
    proxy_url = (proxy_url or "").strip()
    if not proxy_url:
        return ""
    if "://" not in proxy_url:
        proxy_url = f"http://{proxy_url}"
    return proxy_url.rstrip("/")


def _is_local_port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_proxy_url(base_env: Mapping[str, str] | None = None) -> str:
    env = base_env or os.environ

    for key in PROXY_ENV_KEYS:
        proxy_url = normalize_proxy_url(env.get(key))
        if proxy_url:
            return proxy_url

    for port in COMMON_LOCAL_PROXY_PORTS:
        if _is_local_port_open("127.0.0.1", port):
            return f"http://127.0.0.1:{port}"

    return ""


def get_proxy_settings() -> tuple[str, str]:
    from app.common.config import cfg

    return (
        str(cfg.get(cfg.download_proxy_mode) or PROXY_MODE_AUTO),
        str(cfg.get(cfg.download_proxy_url) or ""),
    )


def get_effective_download_proxy_url(
    proxy_mode: str | None = None,
    proxy_url: str | None = None,
    base_env: Mapping[str, str] | None = None,
) -> str:
    proxy_mode = str(proxy_mode or get_proxy_settings()[0] or PROXY_MODE_AUTO)
    proxy_url = proxy_url if proxy_url is not None else get_proxy_settings()[1]

    if proxy_mode == PROXY_MODE_OFF:
        return ""
    if proxy_mode == PROXY_MODE_MANUAL:
        return normalize_proxy_url(proxy_url)
    return detect_proxy_url(base_env)


def build_download_proxy_env(
    proxy_mode: str | None = None,
    proxy_url: str | None = None,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    effective_proxy = get_effective_download_proxy_url(proxy_mode, proxy_url, env)

    for key in PROXY_ENV_KEYS:
        env.pop(key, None)

    if effective_proxy:
        for key in PROXY_ENV_KEYS:
            env[key] = effective_proxy

    env.setdefault("NO_PROXY", "127.0.0.1,localhost")
    env.setdefault("no_proxy", "127.0.0.1,localhost")
    return env


def apply_download_proxy_environment(
    proxy_mode: str | None = None,
    proxy_url: str | None = None,
) -> str:
    env = build_download_proxy_env(proxy_mode, proxy_url)
    for key in PROXY_ENV_KEYS:
        if key in env:
            os.environ[key] = env[key]
        else:
            os.environ.pop(key, None)

    for key in ("NO_PROXY", "no_proxy"):
        if key in env:
            os.environ[key] = env[key]

    return get_effective_download_proxy_url(proxy_mode, proxy_url, env)
