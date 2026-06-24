import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import psutil
import requests
import yt_dlp
from PyQt5.QtCore import QThread, pyqtSignal

from app.config import APP_DATA_PATH
from app.core.utils.logger import setup_logger
from app.core.utils.download_description import write_description_txt_file
from app.core.utils.subtitle_transcript import write_transcript_txt_file
from app.core.utils.proxy_utils import (
    apply_download_proxy_environment,
    get_effective_download_proxy_url,
)
from app.core.utils.macos_video_transcoder import (
    get_native_video_codec,
    is_native_hevc_transcode_supported,
    transcode_video_to_hevc_native,
)
from app.core.utils.video_utils import (
    get_video_codec,
    normalize_video_to_mp4,
    transcode_video_to_hevc,
)

logger = setup_logger("video_download_thread")

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".avi",
    ".flv",
    ".m4v",
}
AUDIO_EXTENSIONS = {
    ".m4a",
    ".mp3",
    ".aac",
    ".wav",
    ".flac",
    ".opus",
    ".ogg",
    ".weba",
    ".webm",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SUBTITLE_EXTENSIONS = {
    ".srt",
    ".vtt",
    ".lrc",
    ".json3",
    ".srv1",
    ".srv2",
    ".srv3",
}
NO_COOKIE_FILE_PATH = APP_DATA_PATH / "__no_cookie__.txt"
SUBTITLE_DOWNLOAD_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
SUBTITLE_DOWNLOAD_RETRY_DELAYS = (0.5, 1.5)


class DownloadCancelledError(Exception):
    """Raised when the user explicitly terminates an in-flight download."""


class FfmpegProgressMonitor:
    """Receive FFmpeg ``-progress`` frames over a local UDP socket."""

    def __init__(self, section_durations: list[float], callback):
        self.section_durations = [max(0.0, float(value)) for value in section_durations]
        self.callback = callback
        self.socket = None
        self.thread = None
        self.stop_event = threading.Event()
        self.started_at = time.monotonic()
        self.section_index = 0
        self.completed_duration = 0.0
        self.processing_started = False

    @property
    def progress_url(self) -> str | None:
        if self.socket is None:
            return None
        return f"udp://127.0.0.1:{self.socket.getsockname()[1]}"

    def start(self) -> bool:
        listening = True
        try:
            progress_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            progress_socket.bind(("127.0.0.1", 0))
            progress_socket.settimeout(0.25)
        except OSError as exc:
            logger.warning("FFmpeg 进度监听不可用，将只显示阶段状态: %s", exc)
            progress_socket = None
            listening = False

        self.socket = progress_socket
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="ffmpeg-progress-monitor",
        )
        self.thread.start()
        return listening

    def stop(self):
        self.stop_event.set()
        progress_socket = self.socket
        self.socket = None
        if progress_socket is not None:
            try:
                progress_socket.close()
            except OSError:
                pass
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=1.0)
        self.thread = None

    def _run(self):
        last_heartbeat = 0.0
        while not self.stop_event.is_set():
            now = time.monotonic()
            if not self.processing_started and now - last_heartbeat >= 1.0:
                self._emit_locating()
                last_heartbeat = now

            progress_socket = self.socket
            if progress_socket is None:
                self.stop_event.wait(0.25)
                continue
            try:
                payload, _address = progress_socket.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return

            frame = {}
            for line in payload.decode("utf-8", errors="replace").splitlines():
                key, separator, value = line.partition("=")
                if separator:
                    frame[key.strip()] = value.strip()
            if frame:
                self._handle_frame(frame)

    def _section_duration(self) -> float:
        if not self.section_durations:
            return 0.0
        index = min(self.section_index, len(self.section_durations) - 1)
        return self.section_durations[index]

    def _emit_locating(self):
        section_count = max(1, len(self.section_durations))
        self.callback(
            {
                "phase": "locating",
                "indeterminate": True,
                "percent": "",
                "speed": "",
                "eta": "",
                "downloaded": "",
                "total": "",
                "elapsed": _format_duration(time.monotonic() - self.started_at),
                "filename": "",
                "section_index": min(self.section_index + 1, section_count),
                "section_count": section_count,
                "status": "正在定位片段起点",
            }
        )

    @staticmethod
    def _parse_speed_factor(value: str) -> float:
        try:
            return float(str(value or "").strip().removesuffix("x"))
        except ValueError:
            return 0.0

    def _handle_frame(self, frame: dict):
        try:
            out_time = max(0.0, float(frame.get("out_time_us") or 0) / 1_000_000)
        except (TypeError, ValueError):
            out_time = 0.0

        if out_time <= 0 and not self.processing_started:
            self._emit_locating()
            return

        self.processing_started = self.processing_started or out_time > 0
        duration = self._section_duration()
        total_duration = sum(self.section_durations)
        processed_duration = self.completed_duration + min(out_time, duration or out_time)
        percent = min(100.0, processed_duration * 100 / total_duration) if total_duration else 0.0
        speed_text = str(frame.get("speed") or "").strip()
        speed_factor = self._parse_speed_factor(speed_text)
        remaining_media = max(0.0, total_duration - processed_duration)
        eta = _format_duration(remaining_media / speed_factor) if speed_factor > 0 else ""
        total_size = _safe_size(frame.get("total_size"))
        section_count = max(1, len(self.section_durations))

        self.callback(
            {
                "phase": "processing",
                "indeterminate": False,
                "percent": f"{percent:.1f}",
                "speed": speed_text,
                "eta": eta,
                "downloaded": _format_bytes(total_size) if total_size else "",
                "total": "",
                "elapsed": _format_duration(time.monotonic() - self.started_at),
                "filename": "",
                "section_index": min(self.section_index + 1, section_count),
                "section_count": section_count,
                "status": "正在下载并生成片段",
            }
        )

        if frame.get("progress") == "end":
            self.completed_duration += duration
            self.section_index += 1
            self.processing_started = False
            if self.section_index < len(self.section_durations):
                self._emit_locating()


def sanitize_filename(name: str, replacement: str = "_") -> str:
    forbidden_chars = r'<>:"/\\|?*'
    sanitized = re.sub(f"[{re.escape(forbidden_chars)}]", replacement, name)
    sanitized = re.sub(r"[\0-\31]", "", sanitized)
    sanitized = sanitized.rstrip(" .")

    max_length = 255
    if len(sanitized) > max_length:
        base, ext = os.path.splitext(sanitized)
        base_max_length = max_length - len(ext)
        sanitized = base[:base_max_length] + ext

    return sanitized or "default_filename"


def _requests_kwargs(proxy_url: str) -> dict:
    if not proxy_url:
        return {}
    return {"proxies": {"http": proxy_url, "https": proxy_url}}


def _safe_size(value) -> int | None:
    if value in (None, "", 0):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_bytes(size: int | None) -> str:
    if not size:
        return "未知大小"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    return f"{value:.1f}{units[unit_index]}"


def _format_duration(seconds) -> str:
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError):
        return "未知时长"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _format_number(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "未知"


def _friendly_codec(codec: str | None) -> str:
    if not codec or codec == "none":
        return ""
    return str(codec).replace(".", " ").upper()


def _format_resolution(item: dict) -> str:
    if item.get("height"):
        return f"{item['height']}p"
    if item.get("width"):
        return f"{item['width']}w"
    return item.get("resolution") or "未知"


def _extract_language(item: dict) -> str:
    language = item.get("language") or item.get("language_preference")
    if language in (None, "", -1):
        return ""
    return str(language).upper()


def _build_format_entry(item: dict) -> dict | None:
    vcodec = item.get("vcodec")
    acodec = item.get("acodec")
    has_video = bool(vcodec and vcodec != "none")
    has_audio = bool(acodec and acodec != "none")
    if not has_video and not has_audio:
        return None

    filesize = _safe_size(item.get("filesize")) or _safe_size(item.get("filesize_approx"))
    fps = item.get("fps")
    abr = item.get("abr") or item.get("tbr")
    ext = item.get("ext") or ""
    dynamic_range = item.get("dynamic_range") or ""

    detail_parts = []
    language = _extract_language(item)
    if language:
        detail_parts.append(language)
    if fps:
        detail_parts.append(f"{int(fps)}FPS")
    if dynamic_range and str(dynamic_range).upper() not in {"SDR", "UNKNOWN"}:
        detail_parts.append(str(dynamic_range).upper())
    if has_video and _friendly_codec(vcodec):
        detail_parts.append(_friendly_codec(vcodec))
    if has_audio and not has_video and _friendly_codec(acodec):
        detail_parts.append(_friendly_codec(acodec))
    if has_video and has_audio:
        detail_parts.append("含音频")
    if ext:
        detail_parts.append(ext)
    detail_parts.append(_format_bytes(filesize))

    quality = _format_resolution(item) if has_video else f"{int(abr)}kbps" if abr else "音频"

    return {
        "format_id": str(item.get("format_id", "")),
        "ext": ext,
        "quality": quality,
        "details": " · ".join(part for part in detail_parts if part),
        "filesize": filesize,
        "fps": fps or 0,
        "height": item.get("height") or 0,
        "width": item.get("width") or 0,
        "abr": abr or 0,
        "language": language,
        "vcodec": vcodec or "",
        "acodec": acodec or "",
        "dynamic_range": dynamic_range or "",
        "has_video": has_video,
        "has_audio": has_audio,
        "channels": item.get("audio_channels") or item.get("channels") or 0,
        "protocol": item.get("protocol") or "",
    }


def normalize_preview_data(url: str, info_dict: dict, thumbnail_bytes: bytes | None = None) -> dict:
    video_formats = []
    audio_formats = []
    for item in info_dict.get("formats") or []:
        entry = _build_format_entry(item)
        if not entry:
            continue
        if entry["has_video"]:
            video_formats.append(entry)
        elif entry["has_audio"]:
            audio_formats.append(entry)

    video_formats.sort(
        key=lambda item: (item.get("height", 0), item.get("fps", 0), item.get("filesize", 0) or 0),
        reverse=True,
    )
    audio_formats.sort(
        key=lambda item: (item.get("abr", 0), item.get("filesize", 0) or 0, item.get("channels", 0)),
        reverse=True,
    )

    subtitles = info_dict.get("subtitles") or {}
    automatic_captions = info_dict.get("automatic_captions") or {}
    return {
        "url": url,
        "title": info_dict.get("title") or "未命名视频",
        "uploader": info_dict.get("uploader") or info_dict.get("channel") or "未知作者",
        "duration_text": _format_duration(info_dict.get("duration")),
        "upload_date": info_dict.get("upload_date") or "",
        "view_count_text": _format_number(info_dict.get("view_count")),
        "thumbnail_url": info_dict.get("thumbnail") or "",
        "thumbnail_bytes": thumbnail_bytes,
        "video_formats": video_formats,
        "audio_formats": audio_formats,
        "manual_subtitle_languages": sorted(subtitles.keys()),
        "auto_subtitle_languages": sorted(automatic_captions.keys()),
        "has_manual_subtitles": bool(subtitles),
        "has_auto_subtitles": bool(automatic_captions),
        "info_dict": info_dict,
    }


def _pick_subtitle_item(
    info_dict: dict, subtitle_mode: str, subtitle_language: str | None
) -> tuple[str | None, str]:
    sources = (
        info_dict.get("subtitles", {})
        if subtitle_mode == "manual"
        else info_dict.get("automatic_captions", {})
    )
    if not sources:
        return None, "vtt"

    preferred_keys = []
    if subtitle_language:
        preferred_keys.append(subtitle_language)
        preferred_keys.extend(
            [key for key in sources.keys() if key.startswith(subtitle_language)]
        )

    candidate_keys = preferred_keys + list(sources.keys())
    seen = set()
    for key in candidate_keys:
        if key in seen or key not in sources:
            continue
        seen.add(key)
        entries = sources.get(key) or []
        if not entries:
            continue
        item = entries[-1]
        url = item.get("url")
        ext = item.get("ext") or "vtt"
        if url:
            return url, ext

    return None, "vtt"


def _download_subtitle_fallback(
    subtitle_download_link: str | None,
    subtitle_ext: str,
    subtitle_path: Path,
    proxy_url: str,
) -> str | None:
    if not subtitle_download_link:
        return None

    attempts = len(SUBTITLE_DOWNLOAD_RETRY_DELAYS) + 1
    last_error: Exception | None = None
    response = None
    for attempt in range(attempts):
        try:
            response = requests.get(
                subtitle_download_link, timeout=30, **_requests_kwargs(proxy_url)
            )
            if response.status_code not in SUBTITLE_DOWNLOAD_RETRY_STATUS:
                response.raise_for_status()
                break
            response.raise_for_status()
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= attempts - 1:
                raise
            delay = SUBTITLE_DOWNLOAD_RETRY_DELAYS[attempt]
            logger.warning(
                "字幕直链下载失败，%.1f 秒后重试（%s/%s）: %s",
                delay,
                attempt + 1,
                attempts,
                exc,
            )
            time.sleep(delay)
    if response is None:
        raise RuntimeError(f"字幕直链下载失败: {last_error}")

    subtitle_path = subtitle_path.with_suffix(f".{subtitle_ext or 'vtt'}")
    subtitle_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = subtitle_path.with_name(f".{subtitle_path.name}.tmp")
    with open(temp_path, "w", encoding="utf-8") as file:
        file.write(response.text)
    os.replace(temp_path, subtitle_path)
    return str(subtitle_path)


def _is_format_selection_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if not message:
        return False
    markers = (
        "requested format is not available",
        "requested format not available",
        "requested format unavailable",
        "format is not available",
        "format not available",
        "format unavailable",
        "requested formats are incompatible",
    )
    if any(marker in message for marker in markers):
        return True
    return bool(re.search(r"\bformat(s)?\b.*\b(not available|unavailable)\b", message))


def _download_thumbnail_fallback(
    thumbnail_url: str | None, thumbnail_path: Path, proxy_url: str
) -> str | None:
    if not thumbnail_url:
        return None
    response = requests.get(thumbnail_url, timeout=30, **_requests_kwargs(proxy_url))
    response.raise_for_status()
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    with open(thumbnail_path, "wb") as file:
        file.write(response.content)
    return str(thumbnail_path)


def _normalize_thumbnail_to_png(thumbnail_path: str | Path | None) -> str | None:
    if not thumbnail_path:
        return None

    path = Path(thumbnail_path)
    if not path.exists():
        return None

    png_path = path.with_suffix(".png")
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.save(png_path, format="PNG")
        if path.resolve() != png_path.resolve() and path.exists():
            path.unlink()
        return str(png_path)
    except Exception as exc:
        logger.warning("封面转换 PNG 失败，保留原文件: %s", exc)
        return str(path)


def _resolve_download_engine_strategy(
    strategy: str | None, proxy_url: str, cookiefile_path: Path
) -> str | None:
    if strategy not in {"单线程", "多线程", "智能选择"}:
        return None
    if strategy != "智能选择":
        return strategy
    if proxy_url or cookiefile_path.exists():
        return "单线程"
    return "多线程"


def _build_strategy_options(strategy: str | None) -> dict:
    if strategy == "单线程":
        return {
            "concurrent_fragment_downloads": 1,
            "retries": 10,
            "fragment_retries": 10,
        }
    if strategy == "多线程":
        return {
            "concurrent_fragment_downloads": 4,
            "retries": 3,
            "fragment_retries": 3,
        }
    return {}


def _build_youtube_challenge_options() -> dict:
    node_path = shutil.which("node")
    if not node_path:
        for candidate in ("/usr/local/bin/node", "/opt/homebrew/bin/node"):
            if Path(candidate).is_file():
                node_path = candidate
                break
    if not node_path:
        return {}
    return {
        "js_runtimes": {
            "node": {
                "path": node_path,
            }
        },
        "remote_components": {"ejs:github"},
    }


def _robust_format_selector(selector: str, download_mode: str = "video_audio") -> str:
    selector = str(selector or "").strip()
    if not selector:
        if download_mode == "audio":
            return "bestaudio/best"
        if download_mode == "video":
            return "bv*/bestvideo/best"
        return "bv*+ba/bestvideo+bestaudio/best"

    if "bv*+ba" in selector:
        return selector

    replacements = {
        "bestvideo+bestaudio/best": "bv*+ba/bestvideo+bestaudio/best",
        "bestvideo/best": "bv*/bestvideo/best",
    }
    if selector in replacements:
        return replacements[selector]

    if download_mode == "video_audio" and "bestvideo+bestaudio/best" in selector:
        return selector.replace(
            "bestvideo+bestaudio/best",
            "bv*+ba/bestvideo+bestaudio/best",
        )
    return selector


def _build_ydl_options(proxy_url: str, cookiefile_path: Path, progress_hooks=None) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
        "nocheckcertificate": False,
    }
    if progress_hooks:
        options["progress_hooks"] = progress_hooks
    if proxy_url:
        options["proxy"] = proxy_url
    if cookiefile_path.exists():
        logger.info("使用 cookiefile: %s", cookiefile_path)
        options["cookiefile"] = str(cookiefile_path)
    else:
        options["extractor_args"] = {
            "youtube": {
                "player_client": ["android", "ios", "tv"],
            }
        }
    options.update(_build_youtube_challenge_options())
    return options


def _has_downloadable_media_formats(info_dict: dict) -> bool:
    for item in info_dict.get("formats") or []:
        vcodec = item.get("vcodec")
        acodec = item.get("acodec")
        if (vcodec and vcodec != "none") or (acodec and acodec != "none"):
            return True
    return False


def _extract_metadata_info(
    url: str,
    proxy_url: str,
    cookiefile_path: Path,
    effective_strategy: str | None,
) -> dict:
    def extract_once(active_cookiefile_path: Path) -> dict:
        options = _build_ydl_options(proxy_url, active_cookiefile_path)
        options.update(_build_strategy_options(effective_strategy))
        options.update(
            {
                "skip_download": True,
                "extract_flat": False,
                "lazy_playlist": False,
            }
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False, process=False)

    info_dict = extract_once(cookiefile_path)

    if not isinstance(info_dict, dict) or not info_dict.get("formats"):
        raise RuntimeError("无法解析可用格式列表")

    if cookiefile_path.exists() and not _has_downloadable_media_formats(info_dict):
        logger.warning("使用 cookies 仅解析到图片格式，改为不带 cookies 重试")
        fallback_info_dict = extract_once(NO_COOKIE_FILE_PATH)
        if isinstance(fallback_info_dict, dict) and _has_downloadable_media_formats(fallback_info_dict):
            fallback_info_dict["_videocaptioner_disable_cookiefile"] = True
            return fallback_info_dict

    return info_dict


def _time_text_to_seconds(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) not in {2, 3} or not all(part.isdigit() for part in parts):
        return None
    try:
        if len(parts) == 2:
            minutes, seconds = map(int, parts)
            hours = 0
        else:
            hours, minutes, seconds = map(int, parts)
    except ValueError:
        return None
    if minutes < 0 or seconds < 0 or seconds >= 60 or (len(parts) == 3 and minutes >= 60):
        return None
    return hours * 3600 + minutes * 60 + seconds


def _parse_download_section(section: str) -> dict | None:
    value = str(section or "").strip()
    if not value.startswith("*") or "-" not in value:
        return None
    time_range = value[1:]
    start_text, end_text = time_range.split("-", 1)
    start_seconds = _time_text_to_seconds(start_text)
    end_seconds = _time_text_to_seconds(end_text)
    if start_seconds is None or end_seconds is None or start_seconds >= end_seconds:
        return None
    return {
        "start_time": start_seconds,
        "end_time": end_seconds,
    }


def _build_download_ranges_callback(download_sections: list[str]):
    parsed_sections = []
    for index, section in enumerate(download_sections or [], start=1):
        parsed = _parse_download_section(section)
        if not parsed:
            raise RuntimeError(f"无效的时间段配置: {section}")
        parsed["title"] = f"section_{index:02d}"
        parsed["index"] = index
        parsed_sections.append(parsed)

    def _callback(_info_dict, _ydl):
        return parsed_sections or [{}]

    return _callback


def _probe_media_streams(media_path: str | Path) -> dict:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,duration:stream_tags=DURATION",
            "-of",
            "json",
            str(media_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return json.loads(completed.stdout or "{}")


def _duration_text_to_seconds(value) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if ":" not in text:
            return float(text)
        hours, minutes, seconds = text.split(":", 2)
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (TypeError, ValueError):
        return None


def _media_has_valid_audio(media_path: str | Path) -> bool:
    try:
        probe = _probe_media_streams(media_path)
    except Exception as exc:
        logger.warning("无法验证下载结果音轨: %s", exc)
        return False

    for stream in probe.get("streams") or []:
        if stream.get("codec_type") != "audio":
            continue
        tag_duration = _duration_text_to_seconds((stream.get("tags") or {}).get("DURATION"))
        stream_duration = _duration_text_to_seconds(stream.get("duration"))
        if tag_duration is not None:
            return tag_duration > 0
        if stream_duration is not None:
            return stream_duration > 0
        # Some valid containers omit both duration fields. An audio stream is
        # still better evidence than rejecting a download we cannot disprove.
        return True
    return False


def _audio_repair_window(
    media_path: str | Path, download_sections: list[str]
) -> tuple[float, float] | None:
    if len(download_sections) != 1:
        return None
    section = _parse_download_section(download_sections[0])
    if not section:
        return None

    probe = _probe_media_streams(media_path)
    media_duration = _duration_text_to_seconds((probe.get("format") or {}).get("duration"))
    requested_duration = float(section["end_time"] - section["start_time"])
    if not media_duration or media_duration <= 0:
        media_duration = requested_duration

    # Stream-copy range downloads can begin at the preceding video keyframe.
    # Extend the audio backwards by the same small pre-roll so A/V stays aligned.
    extra_duration = max(0.0, media_duration - requested_duration)
    pre_roll = min(float(section["start_time"]), extra_duration, 30.0)
    return max(0.0, float(section["start_time"]) - pre_roll), media_duration


def _remux_recovery_audio(
    media_path: str | Path,
    audio_path: str | Path,
    download_sections: list[str],
) -> None:
    media = Path(media_path)
    repaired = media.with_name(f".{media.stem}.audio-repaired{media.suffix}")
    window = _audio_repair_window(media, download_sections)

    command = ["ffmpeg", "-nostdin", "-y", "-i", str(media)]
    if window:
        start_seconds, duration_seconds = window
        command.extend(
            [
                "-ss",
                f"{start_seconds:.3f}",
                "-t",
                f"{duration_seconds:.3f}",
            ]
        )
    command.extend(
        [
            "-i",
            str(audio_path),
            "-map",
            "0",
            "-map",
            "-0:a?",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-shortest",
            str(repaired),
        ]
    )

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if not _media_has_valid_audio(repaired):
            raise RuntimeError("补下载的音频仍为空")
        os.replace(repaired, media)
    finally:
        if repaired.exists():
            repaired.unlink()


def extract_preview(url: str, download_engine_strategy: str | None = None) -> dict:
    proxy_url = apply_download_proxy_environment()
    cookiefile_path = APP_DATA_PATH / "cookies.txt"
    effective_strategy = _resolve_download_engine_strategy(
        download_engine_strategy, proxy_url, cookiefile_path
    )
    info_dict = _extract_metadata_info(
        url, proxy_url, cookiefile_path, effective_strategy
    )

    thumbnail_bytes = None
    thumbnail_url = info_dict.get("thumbnail")
    if thumbnail_url:
        try:
            response = requests.get(
                thumbnail_url, timeout=20, **_requests_kwargs(proxy_url)
            )
            response.raise_for_status()
            thumbnail_bytes = response.content
        except Exception:
            logger.warning("封面预览下载失败: %s", thumbnail_url, exc_info=True)

    return normalize_preview_data(url, info_dict, thumbnail_bytes)


class VideoPreviewThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url: str, download_engine_strategy: str | None = None):
        super().__init__()
        self.url = url
        self.download_engine_strategy = download_engine_strategy

    def run(self):
        try:
            self.finished.emit(extract_preview(self.url, self.download_engine_strategy))
        except Exception as exc:
            logger.exception("解析下载资源失败: %s", exc)
            self.error.emit(str(exc))


class VideoDownloadThread(QThread):
    finished = pyqtSignal(str)
    detailed_finished = pyqtSignal(dict)
    progress = pyqtSignal(int, str)
    progress_detail = pyqtSignal(dict)
    error = pyqtSignal(str)
    cancelled = pyqtSignal(str)

    def __init__(
        self,
        url: str,
        work_dir: str,
        need_video: bool = True,
        need_subtitle: bool = True,
        need_thumbnail: bool = False,
        subtitle_mode: str = "auto",
        download_engine_strategy: str | None = None,
        download_mode: str = "video_audio",
        selected_video_format_id: str = "",
        selected_audio_format_id: str = "",
        format_selector: str = "",
        need_metadata: bool = False,
        need_description_txt: bool = False,
        need_transcript_txt: bool = False,
        enable_time_ranges: bool = False,
        download_sections: list[str] | None = None,
        pr_smart_transcode_hevc_on_av1: bool = False,
        ensure_mp4_output: bool = False,
    ):
        super().__init__()
        self.url = url
        self.work_dir = work_dir
        self.need_video = need_video
        self.need_subtitle = need_subtitle
        self.need_thumbnail = need_thumbnail
        self.subtitle_mode = subtitle_mode if subtitle_mode in {"manual", "auto"} else "auto"
        self.download_engine_strategy = download_engine_strategy
        self.download_mode = download_mode
        self.selected_video_format_id = selected_video_format_id
        self.selected_audio_format_id = selected_audio_format_id
        self.format_selector = format_selector
        self.need_metadata = need_metadata
        self.need_description_txt = need_description_txt
        self.need_transcript_txt = need_transcript_txt
        self.enable_time_ranges = enable_time_ranges
        self.download_sections = list(download_sections or [])
        self.pr_smart_transcode_hevc_on_av1 = pr_smart_transcode_hevc_on_av1
        self.ensure_mp4_output = ensure_mp4_output
        self._pause_event = threading.Event()
        self._terminate_event = threading.Event()
        self._pause_notice_emitted = False
        self._current_progress = 0
        self._download_root = Path(work_dir)
        self._download_dir = None
        self._download_dir_existed = False
        self._download_started_at = None
        self._download_processes_done = threading.Event()
        self._download_processes_done.set()
        self._cleanup_lock = threading.Lock()
        self._cleanup_completed = False
        self._cleanup_message = ""

    def run(self):
        try:
            result = self.download(
                need_video=self.need_video,
                need_subtitle=self.need_subtitle,
                need_thumbnail=self.need_thumbnail,
                subtitle_mode=self.subtitle_mode,
                need_metadata=self.need_metadata,
                need_description_txt=self.need_description_txt,
                need_transcript_txt=self.need_transcript_txt,
                enable_time_ranges=self.enable_time_ranges,
                download_sections=self.download_sections,
                pr_smart_transcode_hevc_on_av1=self.pr_smart_transcode_hevc_on_av1,
                ensure_mp4_output=self.ensure_mp4_output,
            )
            self.detailed_finished.emit(result)
            self.finished.emit(result.get("video_path") or "")
        except DownloadCancelledError as exc:
            self._wait_for_download_subprocesses()
            message = self._cleanup_partial_download(str(exc))
            logger.info(message)
            self.cancelled.emit(message)
        except Exception as exc:
            if self._terminate_event.is_set():
                self._wait_for_download_subprocesses()
                message = self._cleanup_partial_download(self.tr("下载已终止，已清理当前下载数据。"))
                logger.info("%s", message)
                self.cancelled.emit(message)
                return
            logger.exception("下载资源失败: %s", exc)
            self.error.emit(str(exc))

    def request_pause(self):
        if not self._terminate_event.is_set():
            self._pause_event.set()

    def request_terminate(self):
        self._terminate_event.set()
        self._pause_event.clear()
        self._terminate_download_subprocesses()

    def _terminate_download_subprocesses(self):
        """Stop FFmpeg processes that yt-dlp started for this download.

        Time-range downloads are handed off to FFmpeg. While FFmpeg is blocked in
        network I/O, yt-dlp does not invoke progress hooks, so setting the cancel
        event alone cannot interrupt the download thread.
        """
        target = self._download_dir
        if not target:
            self._download_processes_done.set()
            return

        try:
            target_path = str(Path(target).resolve(strict=False))
            target_prefix = target_path.rstrip(os.sep) + os.sep
            children = psutil.Process(os.getpid()).children(recursive=True)
        except (OSError, psutil.Error) as exc:
            logger.warning("无法枚举下载子进程: %s", exc)
            self._download_processes_done.set()
            return

        processes = []
        for process in children:
            try:
                process_name = process.name().lower()
                command = [str(arg) for arg in process.cmdline()]
                executable_name = Path(command[0]).name.lower() if command else ""
                is_ffmpeg = process_name in {"ffmpeg", "ffmpeg.exe"} or executable_name in {
                    "ffmpeg",
                    "ffmpeg.exe",
                }
                targets_download = any(target_prefix in arg for arg in command[1:])
                if not is_ffmpeg or not targets_download:
                    continue

                processes.append(process)
            except (OSError, psutil.Error):
                continue

        if not processes:
            self._download_processes_done.set()
            return

        self._download_processes_done.clear()
        for process in processes:
            try:
                process.terminate()
                logger.info("已请求终止下载 FFmpeg 子进程: pid=%s", process.pid)
            except (OSError, psutil.Error):
                continue
        try:
            threading.Thread(
                target=self._finish_download_subprocess_termination,
                args=(processes,),
                daemon=True,
                name="video-download-process-cleanup",
            ).start()
        except Exception as exc:
            logger.warning("无法启动下载子进程清理线程，将同步等待: %s", exc)
            self._finish_download_subprocess_termination(processes)

    def _finish_download_subprocess_termination(self, processes):
        try:
            self._kill_download_subprocesses_after_timeout(processes)
        finally:
            self._download_processes_done.set()

    def _wait_for_download_subprocesses(self):
        event = getattr(self, "_download_processes_done", None)
        if event is not None:
            event.wait(timeout=4.0)

    @staticmethod
    def _kill_download_subprocesses_after_timeout(processes):
        try:
            _, alive = psutil.wait_procs(processes, timeout=1.5)
        except psutil.Error as exc:
            logger.warning("等待下载子进程退出失败: %s", exc)
            alive = processes

        for process in alive:
            try:
                process.kill()
                logger.warning("强制结束未响应的下载 FFmpeg 子进程: pid=%s", process.pid)
            except (OSError, psutil.Error):
                continue

    def _raise_if_terminated(self):
        if self._terminate_event.is_set():
            raise DownloadCancelledError("下载已终止，正在清理当前下载数据。")

    def _cleanup_partial_download(self, default_message: str) -> str:
        cleanup_lock = getattr(self, "_cleanup_lock", None)
        if cleanup_lock is None:
            cleanup_lock = threading.Lock()
            self._cleanup_lock = cleanup_lock
        with cleanup_lock:
            if getattr(self, "_cleanup_completed", False):
                return getattr(self, "_cleanup_message", "") or default_message
            message = self._cleanup_partial_download_once(default_message)
            self._cleanup_completed = True
            self._cleanup_message = message
            return message

    def _cleanup_partial_download_once(self, default_message: str) -> str:
        target = self._download_dir
        base_dir = self._download_root
        if not target:
            return default_message

        try:
            base_resolved = base_dir.resolve(strict=False)
            target_resolved = target.resolve(strict=False)
            target_resolved.relative_to(base_resolved)
        except (OSError, ValueError):
            logger.warning("跳过清理下载目录，路径校验失败: base=%s target=%s", base_dir, target)
            return default_message

        if target_resolved == base_resolved:
            logger.warning("跳过清理下载目录，目标目录与输出根目录相同: %s", target_resolved)
            return default_message

        try:
            if not target_resolved.exists():
                return default_message

            if not self._download_dir_existed:
                shutil.rmtree(target_resolved)
                return "下载已终止，已清理当前下载目录。"

            cutoff = (self._download_started_at or time.time()) - 1
            files = sorted(
                (path for path in target_resolved.rglob("*") if path.is_file()),
                key=lambda path: len(path.parts),
                reverse=True,
            )
            removed_count = 0
            for path in files:
                try:
                    if path.stat().st_mtime >= cutoff:
                        path.unlink(missing_ok=True)
                        removed_count += 1
                except FileNotFoundError:
                    continue

            directories = sorted(
                (path for path in target_resolved.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            )
            for directory in directories:
                try:
                    directory.rmdir()
                except OSError:
                    continue

            return (
                "下载已终止，已清理当前下载产生的数据。"
                if removed_count
                else default_message
            )
        except Exception as exc:
            logger.warning("清理下载目录失败: %s", exc)
            return f"{default_message} 清理残留时遇到问题: {exc}"

    def progress_hook(self, data):
        if data.get("status") != "downloading":
            return
        percent = data.get("_percent_str", "0")
        speed = data.get("_speed_str", "0")
        eta = data.get("_eta_str", "")
        downloaded_bytes = data.get("_downloaded_bytes_str", "")
        total_bytes = data.get("_total_bytes_str", "") or data.get("_total_bytes_estimate_str", "")
        elapsed = data.get("_elapsed_str", "")
        filename = data.get("filename") or data.get("info_dict", {}).get("title") or ""
        clean_percent = (
            str(percent).replace("\x1b[0;94m", "").replace("\x1b[0m", "").strip().replace("%", "")
        )
        clean_speed = str(speed).replace("\x1b[0;32m", "").replace("\x1b[0m", "").strip()
        clean_eta = str(eta).strip()
        clean_downloaded = str(downloaded_bytes).strip()
        clean_total = str(total_bytes).strip()
        clean_elapsed = str(elapsed).strip()

        try:
            progress_value = int(float(clean_percent))
        except ValueError:
            progress_value = 0
        self._current_progress = progress_value
        detail_payload = {
            "percent": clean_percent,
            "speed": clean_speed,
            "eta": clean_eta,
            "downloaded": clean_downloaded,
            "total": clean_total,
            "elapsed": clean_elapsed,
            "filename": str(filename),
        }
        self.progress_detail.emit(detail_payload)

        self._raise_if_terminated()

        if self._pause_event.is_set():
            if not self._pause_notice_emitted:
                self._pause_notice_emitted = True
                self.progress.emit(
                    self._current_progress,
                    "下载已暂停，再次点击按钮将终止下载并清理当前数据。",
                )
            while self._pause_event.is_set():
                self._raise_if_terminated()
                time.sleep(0.2)

        self.progress.emit(progress_value, f"下载进度: {clean_percent}%  速度: {clean_speed}")

    def _emit_range_progress_detail(self, detail: dict):
        if not self._terminate_event.is_set():
            self.progress_detail.emit(detail)

    def _range_section_durations(self) -> list[float]:
        durations = []
        for section in self.download_sections:
            parsed = _parse_download_section(section)
            if parsed:
                durations.append(float(parsed["end_time"] - parsed["start_time"]))
        return durations

    def _range_phase_detail(self, phase: str, status: str, *, indeterminate: bool) -> dict:
        return {
            "phase": phase,
            "indeterminate": indeterminate,
            "percent": "",
            "speed": "",
            "eta": "",
            "downloaded": "",
            "total": "",
            "elapsed": "00:00",
            "filename": "",
            "section_index": 1,
            "section_count": max(1, len(self.download_sections)),
            "status": status,
        }

    def _default_format_selector(self) -> str:
        return _robust_format_selector("", self.download_mode)

    def _fallback_format_selector(self) -> str:
        if self.ensure_mp4_output and self.download_mode == "video_audio":
            return (
                "bv*[ext=mp4]+ba[ext=m4a]/"
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "best[ext=mp4]/"
                "bv*+ba/bestvideo+bestaudio/best"
            )
        return self._default_format_selector()

    def _effective_format_selector(self) -> str:
        if self.format_selector:
            return _robust_format_selector(self.format_selector, self.download_mode)
        if self.download_mode == "audio":
            return _robust_format_selector(
                self.selected_audio_format_id or self._default_format_selector(),
                self.download_mode,
            )
        if self.download_mode == "video":
            return _robust_format_selector(
                self.selected_video_format_id or self._default_format_selector(),
                self.download_mode,
            )
        if self.selected_video_format_id and self.selected_audio_format_id:
            return f"{self.selected_video_format_id}+{self.selected_audio_format_id}"
        if self.selected_video_format_id:
            return self.selected_video_format_id
        return self._default_format_selector()

    def _find_main_media_files(self, work_dir: Path) -> list[str]:
        candidates = []
        for file in work_dir.rglob("*"):
            if not file.is_file():
                continue
            if "subtitle" in {part.lower() for part in file.parts}:
                continue
            suffix = file.suffix.lower()
            if suffix in IMAGE_EXTENSIONS or suffix in SUBTITLE_EXTENSIONS:
                continue
            if suffix in {".json", ".part", ".ytdl", ".tmp", ".txt"}:
                continue
            candidates.append(file)

        if not candidates:
            return []

        if self.download_mode == "audio":
            audio_candidates = [file for file in candidates if file.suffix.lower() in AUDIO_EXTENSIONS]
            if audio_candidates:
                candidates = audio_candidates
        else:
            video_candidates = [file for file in candidates if file.suffix.lower() in VIDEO_EXTENSIONS]
            if video_candidates:
                candidates = video_candidates

        candidates.sort(key=lambda file: (file.stat().st_size, file.stat().st_mtime), reverse=True)
        return [str(file) for file in candidates]

    def _find_main_media_file(self, work_dir: Path) -> str | None:
        media_files = self._find_main_media_files(work_dir)
        return media_files[0] if media_files else None

    def _recover_missing_audio(
        self,
        media_path: str,
        proxy_url: str,
        cookiefile_path: Path,
        work_dir: Path,
        download_sections: list[str],
    ) -> None:
        audio_selector = self.selected_audio_format_id or "bestaudio[ext=m4a]/bestaudio"
        self.progress.emit(96, self.tr("检测到空音轨，正在仅补下载音频..."))
        logger.warning(
            "下载结果缺少有效音频，开始仅补下载音频: media=%s format=%s",
            media_path,
            audio_selector,
        )

        with tempfile.TemporaryDirectory(
            prefix=".videocaptioner-audio-recovery-", dir=work_dir
        ) as temp_dir:
            recovery_options = _build_ydl_options(proxy_url, cookiefile_path)
            recovery_options.update(_build_strategy_options("单线程"))
            recovery_options.update(
                {
                    "format": audio_selector,
                    "outtmpl": {"default": "audio.%(ext)s"},
                    "paths": {"home": temp_dir},
                    "noplaylist": True,
                }
            )
            with yt_dlp.YoutubeDL(recovery_options) as ydl:
                ydl.download([self.url])

            audio_files = [
                path
                for path in Path(temp_dir).iterdir()
                if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
            ]
            if not audio_files:
                raise RuntimeError("音频补下载完成，但没有找到音频文件")
            audio_files.sort(key=lambda path: path.stat().st_size, reverse=True)
            _remux_recovery_audio(media_path, audio_files[0], download_sections)
        logger.info("空音轨已自动修复: %s", media_path)

    def _write_metadata_file(self, info_dict: dict, work_dir: Path) -> str:
        metadata_path = work_dir / f"{sanitize_filename(info_dict.get('title', 'video'))}.info.json"
        work_dir.mkdir(parents=True, exist_ok=True)
        with open(metadata_path, "w", encoding="utf-8") as file:
            json.dump(info_dict, file, ensure_ascii=False, indent=2, default=str)
        return str(metadata_path)

    def _write_description_txt_file(self, info_dict: dict, work_dir: Path) -> str:
        return write_description_txt_file(
            info_dict,
            work_dir,
            sanitize_filename(info_dict.get("title", "video")),
        )

    def _write_transcript_txt_file(self, subtitle_path: str, info_dict: dict, work_dir: Path) -> str:
        return write_transcript_txt_file(
            subtitle_path,
            work_dir,
            sanitize_filename(info_dict.get("title", "video")),
        )

    def _postprocess_pr_smart_hevc(
        self, video_path: str | None
    ) -> tuple[str | None, str | None, str, bool, str | None, str | None]:
        if not self.pr_smart_transcode_hevc_on_av1:
            return None, None, "未启用", False, None, None
        if not video_path:
            return None, None, "未找到可转码的视频", False, None, None

        source_path = Path(video_path)
        target_path = source_path.with_name(f"{source_path.stem}-hevc.mp4")

        native_supported = is_native_hevc_transcode_supported()
        codec = ""
        if native_supported:
            try:
                codec = get_native_video_codec(str(source_path))
            except Exception as exc:
                logger.warning("macOS 原生编码检测失败，改用 FFmpeg 探测: %s", exc)
        if not codec:
            codec = get_video_codec(str(source_path))
        if codec not in {"av1", "vp9"}:
            return None, None, f"未触发，当前编码为 {codec or '未知'}", False, None, None

        native_error: Exception | None = None
        if native_supported:
            try:
                encoder = transcode_video_to_hevc_native(
                    str(source_path),
                    str(target_path),
                    progress_callback=self.progress.emit,
                )
                return (
                    str(target_path),
                    encoder,
                    f"已使用 macOS 原生 API 转码为 H.265",
                    False,
                    None,
                    None,
                )
            except Exception as exc:
                native_error = exc
                logger.exception("macOS 原生 H.265 后处理失败，改用 FFmpeg 重试: %s", exc)
                self.progress.emit(0, "macOS 原生 H.265 失败，正在使用 FFmpeg 重试...")

        try:
            encoder = transcode_video_to_hevc(
                str(source_path),
                str(target_path),
                progress_callback=self.progress.emit,
                transcode_audio_to_aac=True,
            )
        except Exception as exc:
            logger.exception("FFmpeg H.265 后处理失败: %s", exc)
            message = f"FFmpeg H.265 后处理失败，可手动重试: {exc}"
            if native_error is not None:
                message = (
                    f"macOS 原生 H.265 后处理失败，FFmpeg 重试也失败: "
                    f"{native_error}; {exc}"
                )
            return (
                None,
                None,
                message,
                True,
                str(source_path),
                str(target_path),
            )

        if native_error is not None:
            message = f"macOS 原生失败，已使用 FFmpeg 转码为 H.265（{encoder}）"
        else:
            message = f"已使用 FFmpeg 转码为 H.265（{encoder}）"
        return str(target_path), encoder, message, False, None, None

    def download(
        self,
        need_video: bool = True,
        need_subtitle: bool = True,
        need_thumbnail: bool = False,
        subtitle_mode: str = "auto",
        need_metadata: bool = False,
        need_description_txt: bool = False,
        need_transcript_txt: bool = False,
        enable_time_ranges: bool = False,
        download_sections: list[str] | None = None,
        pr_smart_transcode_hevc_on_av1: bool = False,
        ensure_mp4_output: bool = False,
    ) -> dict:
        logger.info("开始下载资源: %s", self.url)
        self._download_started_at = time.time()
        self._raise_if_terminated()
        proxy_url = apply_download_proxy_environment()
        cookiefile_path = APP_DATA_PATH / "cookies.txt"
        effective_strategy = _resolve_download_engine_strategy(
            self.download_engine_strategy, proxy_url, cookiefile_path
        )
        if effective_strategy:
            logger.info("下载引擎策略: %s", effective_strategy)

        info_dict = _extract_metadata_info(
            self.url, proxy_url, cookiefile_path, effective_strategy
        )
        active_cookiefile_path = (
            NO_COOKIE_FILE_PATH
            if info_dict.get("_videocaptioner_disable_cookiefile")
            else cookiefile_path
        )
        self._raise_if_terminated()
        title = sanitize_filename(info_dict.get("title", "MyVideo"))
        work_dir = Path(self.work_dir) / title
        self._download_dir = work_dir
        self._download_dir_existed = work_dir.exists()
        work_dir.mkdir(parents=True, exist_ok=True)
        self._raise_if_terminated()

        subtitle_language = info_dict.get("language")
        if subtitle_language:
            subtitle_language = str(subtitle_language).lower().split("-")[0]

        subtitle_download_link = None
        subtitle_ext = "vtt"
        effective_need_subtitle = need_subtitle or need_transcript_txt

        if effective_need_subtitle:
            subtitle_download_link, subtitle_ext = _pick_subtitle_item(
                info_dict, subtitle_mode, subtitle_language
            )

        fallback_proxy = proxy_url or get_effective_download_proxy_url()
        subtitle_path = None
        transcript_txt_path = None
        transcript_message = "未触发"
        terms_txt_path = None
        terms_message = "请在 WhisperX 热词管理中手动生成"
        if need_transcript_txt:
            self.progress.emit(2, self.tr("提前下载字幕并生成视频文稿..."))
            try:
                subtitle_path = _download_subtitle_fallback(
                    subtitle_download_link,
                    subtitle_ext,
                    work_dir / "subtitle" / f"【下载字幕】_{subtitle_language or subtitle_mode}",
                    fallback_proxy,
                )
                if subtitle_path:
                    transcript_txt_path = self._write_transcript_txt_file(
                        subtitle_path, info_dict, work_dir
                    )
                    transcript_message = "已提前生成"
                else:
                    transcript_message = "未找到可提前下载的字幕，稍后尝试生成视频文稿"
            except Exception as exc:
                logger.exception("提前生成视频文稿失败: %s", exc)
                transcript_message = f"提前生成视频文稿失败，稍后重试: {exc}"
            self._raise_if_terminated()

        ydl_need_subtitle = effective_need_subtitle and not subtitle_path
        options = _build_ydl_options(
            proxy_url, active_cookiefile_path, progress_hooks=[self.progress_hook]
        )
        options.update(_build_strategy_options(effective_strategy))
        options.update(
            {
                "outtmpl": {
                    "default": "%(title)s.%(ext)s",
                    "subtitle": "【下载字幕】.%(ext)s",
                    "thumbnail": "thumbnail",
                },
                "writesubtitles": ydl_need_subtitle and subtitle_mode == "manual",
                "writeautomaticsub": ydl_need_subtitle and subtitle_mode == "auto",
                "writethumbnail": need_thumbnail,
                "thumbnail_format": "png",
                "skip_download": not need_video,
            }
        )
        if need_video:
            options["format"] = self._effective_format_selector()
            logger.info("使用 format 选择器: %s", options["format"])
            if enable_time_ranges and download_sections:
                options["download_ranges"] = _build_download_ranges_callback(download_sections)
                logger.info("使用时间段下载: %s", " | ".join(download_sections))

        options["paths"] = {
            "home": str(work_dir),
            "subtitle": str(work_dir / "subtitle"),
            "thumbnail": str(work_dir),
        }

        ffmpeg_progress_monitor = None
        if need_video and enable_time_ranges and download_sections:
            self._emit_range_progress_detail(
                self._range_phase_detail("preparing", "正在准备片段", indeterminate=True)
            )
            ffmpeg_progress_monitor = FfmpegProgressMonitor(
                self._range_section_durations(),
                self._emit_range_progress_detail,
            )
            if ffmpeg_progress_monitor.start() and ffmpeg_progress_monitor.progress_url:
                options["external_downloader_args"] = {
                    "ffmpeg_o": [
                        "-progress",
                        ffmpeg_progress_monitor.progress_url,
                        "-nostats",
                    ]
                }
            self._emit_range_progress_detail(
                self._range_phase_detail("locating", "正在定位片段起点", indeterminate=True)
            )

        try:
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([self.url])
            except yt_dlp.utils.DownloadError as exc:
                fallback_selector = self._fallback_format_selector()
                current_selector = str(options.get("format") or "")
                if (
                    need_video
                    and fallback_selector
                    and fallback_selector != current_selector
                    and _is_format_selection_error(exc)
                ):
                    logger.warning(
                        "指定格式不可用，改用默认格式选择器重试: %s -> %s",
                        current_selector,
                        fallback_selector,
                    )
                    options["format"] = fallback_selector
                    with yt_dlp.YoutubeDL(options) as ydl:
                        ydl.download([self.url])
                else:
                    raise
        finally:
            if ffmpeg_progress_monitor is not None:
                ffmpeg_progress_monitor.stop()
        self._raise_if_terminated()

        media_files = self._find_main_media_files(work_dir) if need_video else []
        if need_video and self.download_mode == "video_audio" and media_files:
            invalid_audio_files = [
                path for path in media_files if not _media_has_valid_audio(path)
            ]
            if len(media_files) == 1 and invalid_audio_files:
                self._recover_missing_audio(
                    media_files[0],
                    proxy_url,
                    active_cookiefile_path,
                    work_dir,
                    list(download_sections or []),
                )
            elif invalid_audio_files:
                raise RuntimeError(
                    "下载结果中有文件缺少有效音频轨，多个片段无法自动配对修复"
                )
        mp4_normalization_message = None
        if (
            ensure_mp4_output
            and self.download_mode != "audio"
            and len(media_files) == 1
            and Path(media_files[0]).suffix.lower() != ".mp4"
        ):
            source_path = Path(media_files[0])
            target_path = source_path.with_suffix(".mp4")
            self.progress.emit(97, self.tr("正在将回退格式转换为 MP4..."))
            encoder = normalize_video_to_mp4(
                str(source_path),
                str(target_path),
                progress_callback=self.progress.emit,
                force_hevc_for_codecs={"av1", "vp9"},
            )
            source_path.unlink()
            media_files = [str(target_path)]
            mp4_normalization_message = f"已将回退格式转换为 MP4（{encoder}）"
        media_path = media_files[0] if len(media_files) == 1 else (str(work_dir) if media_files else None)
        if not subtitle_path:
            for file in work_dir.glob("**/【下载字幕】.*"):
                subtitle_path = str(file)
                break

        if effective_need_subtitle and not subtitle_path:
            subtitle_path = _download_subtitle_fallback(
                subtitle_download_link,
                subtitle_ext,
                work_dir / "subtitle" / f"【下载字幕】_{subtitle_language or subtitle_mode}",
                fallback_proxy,
            )

        thumbnail_path = None
        for file in work_dir.glob("**/thumbnail*"):
            thumbnail_path = str(file)
            break

        if need_thumbnail and not thumbnail_path:
            thumbnail_path = _download_thumbnail_fallback(
                info_dict.get("thumbnail"),
                work_dir / "thumbnail.jpg",
                fallback_proxy,
            )
        thumbnail_path = _normalize_thumbnail_to_png(thumbnail_path)

        metadata_path = self._write_metadata_file(info_dict, work_dir) if need_metadata else None
        description_txt_path = (
            self._write_description_txt_file(info_dict, work_dir)
            if need_video and need_description_txt
            else None
        )
        if need_transcript_txt and not transcript_txt_path:
            if subtitle_path:
                try:
                    transcript_txt_path = self._write_transcript_txt_file(
                        subtitle_path, info_dict, work_dir
                    )
                    transcript_message = "已生成"
                except Exception as exc:
                    logger.exception("视频文稿生成失败: %s", exc)
                    transcript_message = f"视频文稿生成失败: {exc}"
            else:
                transcript_message = "未下载到字幕，无法生成视频文稿"
        multi_media = len(media_files) > 1
        original_video_path = media_files[0] if self.download_mode != "audio" and len(media_files) == 1 else None
        transcoded_video_path = None
        transcoded_video_codec = None
        postprocess_message = "未触发"
        postprocess_failed = False
        postprocess_fallback_source_path = None
        postprocess_fallback_target_path = None
        preferred_media_path = media_path
        if need_video and not multi_media and self.download_mode != "audio" and pr_smart_transcode_hevc_on_av1:
            if enable_time_ranges and download_sections:
                self._emit_range_progress_detail(
                    self._range_phase_detail("postprocessing", "正在后处理", indeterminate=True)
                )
            try:
                (
                    transcoded_video_path,
                    transcoded_video_codec,
                    postprocess_message,
                    postprocess_failed,
                    postprocess_fallback_source_path,
                    postprocess_fallback_target_path,
                ) = self._postprocess_pr_smart_hevc(
                    original_video_path
                )
                if transcoded_video_path:
                    preferred_media_path = transcoded_video_path
                elif mp4_normalization_message:
                    postprocess_message = mp4_normalization_message
            except Exception as exc:
                logger.exception("PR智能预设后处理失败: %s", exc)
                postprocess_message = f"H.265 后处理失败: {exc}"
                postprocess_failed = True
                if original_video_path:
                    source_path = Path(original_video_path)
                    postprocess_fallback_source_path = str(source_path)
                    postprocess_fallback_target_path = str(
                        source_path.with_name(f"{source_path.stem}-hevc.mp4")
                    )
        elif mp4_normalization_message:
            postprocess_message = mp4_normalization_message

        result = {
            "video_path": transcoded_video_path or original_video_path,
            "audio_path": media_files[0] if self.download_mode == "audio" and len(media_files) == 1 else None,
            "media_path": preferred_media_path,
            "media_paths": media_files,
            "original_video_path": original_video_path,
            "transcoded_video_path": transcoded_video_path,
            "transcoded_video_codec": transcoded_video_codec,
            "postprocess_message": postprocess_message,
            "postprocess_failed": postprocess_failed,
            "postprocess_fallback_source_path": postprocess_fallback_source_path,
            "postprocess_fallback_target_path": postprocess_fallback_target_path,
            "subtitle_path": subtitle_path,
            "thumbnail_path": thumbnail_path,
            "metadata_path": metadata_path,
            "description_txt_path": description_txt_path,
            "transcript_txt_path": transcript_txt_path,
            "transcript_message": transcript_message,
            "terms_txt_path": terms_txt_path,
            "terms_message": terms_message,
            "info_dict": info_dict,
            "work_dir": str(work_dir),
            "url": self.url,
            "download_mode": self.download_mode,
            "format_selector": self._effective_format_selector() if need_video else "",
            "download_sections": list(download_sections or []),
            "has_multiple_media_files": multi_media,
        }
        logger.info(
            "下载完成: media=%s media_count=%s subtitle=%s thumbnail=%s metadata=%s description_txt=%s transcript_txt=%s terms_txt=%s",
            result["media_path"],
            len(media_files),
            subtitle_path,
            thumbnail_path,
            metadata_path,
            description_txt_path,
            transcript_txt_path,
            terms_txt_path,
        )
        return result
