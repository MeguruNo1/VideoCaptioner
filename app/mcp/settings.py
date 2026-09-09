"""Read the desktop application's persisted settings for headless MCP jobs."""
import json
from pathlib import Path

from .terms import DEFAULT_GLOSSARY_PATH


SETTINGS_PATH = Path.home() / "Library/Application Support/VideoCaptioner/settings.json"


def read_shared_settings(path=SETTINGS_PATH):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _number(value, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def workflow_settings_snapshot(settings):
    """Normalize a JSON-safe snapshot so one job cannot change midway through."""
    download = settings.get("Download") or {}
    mlx = settings.get("MLXWhisper") or {}
    subtitle = settings.get("Subtitle") or {}
    strategy = download.get("EngineStrategy", "智能选择")
    if strategy not in {"单线程", "多线程", "智能选择"}:
        strategy = "智能选择"
    return {
        "schema_version": 1,
        "settings_path": str(SETTINGS_PATH),
        "download": {
            "engine_strategy": strategy,
            "native_hevc_preset": download.get("NativeHevcPreset", "highest_quality"),
            "auto_refresh_cookies": bool(download.get("AutoRefreshEdgeCookies", False)),
            "cookie_browser": download.get("CookieBrowser", "Safari"),
        },
        "mlx": {
            "model": mlx.get("Model") or "mlx-community/whisper-large-v3-turbo",
            "initial_prompt": str(mlx.get("InitialPrompt") or ""),
            "hotwords": str(mlx.get("Hotwords") or ""),
            "vad_enabled": bool(mlx.get("VadEnabled", True)),
            "vad_threshold": _number(mlx.get("VadThreshold"), 0.5, 0.0, 1.0),
            "chunk_duration": int(_number(mlx.get("ChunkDuration"), 600, 60, 1800)),
            "chunk_overlap": int(_number(mlx.get("ChunkOverlap"), 30, 0, 300)),
        },
        "subtitle": {
            "glossary_path": str(Path(subtitle.get("TermGlossaryPath") or DEFAULT_GLOSSARY_PATH).expanduser()),
            "target_language": subtitle.get("TargetLanguage", "中文"),
            "split_type": subtitle.get("SplitType", "句子分段"),
            "max_word_count_cjk": int(_number(subtitle.get("MaxWordCountCJK"), 25, 1, 500)),
            "max_word_count_english": int(_number(subtitle.get("MaxWordCountEnglish"), 20, 1, 500)),
            "mask_original_profanity": bool(subtitle.get("NeedMaskOriginalProfanity", False)),
            "remove_translated_chinese_commas": bool(subtitle.get("NeedsRemoveTranslatedChineseCommas", False)),
            "remove_translated_periods": bool(subtitle.get("NeedsRemovePunctuation", True)),
            "custom_prompt_text": str(subtitle.get("CustomPromptText") or ""),
        },
    }
