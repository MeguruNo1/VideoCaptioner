# coding:utf-8
from enum import Enum

from PyQt5.QtCore import QLocale
from PyQt5.QtGui import QColor
import openai
from qfluentwidgets import (
    qconfig,
    QConfig,
    ConfigItem,
    OptionsConfigItem,
    BoolValidator,
    OptionsValidator,
    RangeConfigItem,
    RangeValidator,
    Theme,
    FolderValidator,
    ConfigSerializer,
    EnumSerializer,
)

from app.config import WORK_PATH, SETTINGS_PATH, MODEL_PATH
from ..core.entities import (
    LLMServiceEnum,
    SplitTypeEnum,
    TargetLanguageEnum,
    TranscribeModelEnum,
    TranscribeLanguageEnum,
    TranslatorServiceEnum,
    WhisperModelEnum,
    FasterWhisperModelEnum,
    VadMethodEnum,
)


class Language(Enum):
    """软件语言"""

    CHINESE_SIMPLIFIED = QLocale(QLocale.Chinese, QLocale.China)
    CHINESE_TRADITIONAL = QLocale(QLocale.Chinese, QLocale.HongKong)
    ENGLISH = QLocale(QLocale.English)
    AUTO = QLocale()


class SubtitleLayoutEnum(Enum):
    """字幕布局"""

    TRANSLATE_ON_TOP = "译文在上"
    ORIGINAL_ON_TOP = "原文在上"
    ONLY_ORIGINAL = "仅原文"
    ONLY_TRANSLATE = "仅译文"
    SEPARATE_ORIGINAL_TRANSLATE = "单独输出原文和译文"


class LanguageSerializer(ConfigSerializer):
    """Language serializer"""

    def serialize(self, language):
        return language.value.name() if language != Language.AUTO else "Auto"

    def deserialize(self, value: str):
        return Language(QLocale(value)) if value != "Auto" else Language.AUTO


class Config(QConfig):
    """应用配置"""

    # LLM配置
    llm_service = OptionsConfigItem(
        "LLM",
        "LLMService",
        LLMServiceEnum.PUBLIC,
        OptionsValidator(LLMServiceEnum),
        EnumSerializer(LLMServiceEnum),
    )

    openai_model = ConfigItem("LLM", "OpenAI_Model", "gpt-4o-mini")
    openai_api_key = ConfigItem("LLM", "OpenAI_API_Key", "")
    openai_api_base = ConfigItem("LLM", "OpenAI_API_Base", "https://api.openai.com/v1")

    silicon_cloud_model = ConfigItem("LLM", "SiliconCloud_Model", "gpt-4o-mini")
    silicon_cloud_api_key = ConfigItem("LLM", "SiliconCloud_API_Key", "")
    silicon_cloud_api_base = ConfigItem(
        "LLM", "SiliconCloud_API_Base", "https://api.siliconflow.cn/v1"
    )

    deepseek_model = ConfigItem("LLM", "DeepSeek_Model", "v4-pro")
    deepseek_api_key = ConfigItem("LLM", "DeepSeek_API_Key", "")
    deepseek_api_base = ConfigItem(
        "LLM", "DeepSeek_API_Base", "https://api.deepseek.com/v1"
    )

    ollama_model = ConfigItem("LLM", "Ollama_Model", "llama2")
    ollama_api_key = ConfigItem("LLM", "Ollama_API_Key", "ollama")
    ollama_api_base = ConfigItem("LLM", "Ollama_API_Base", "http://localhost:11434/v1")

    lm_studio_model = ConfigItem("LLM", "LmStudio_Model", "qwen2.5:7b")
    lm_studio_api_key = ConfigItem("LLM", "LmStudio_API_Key", "lmstudio")
    lm_studio_api_base = ConfigItem(
        "LLM", "LmStudio_API_Base", "http://localhost:1234/v1"
    )

    gemini_model = ConfigItem("LLM", "Gemini_Model", "gemini-pro")
    gemini_api_key = ConfigItem("LLM", "Gemini_API_Key", "")
    gemini_api_base = ConfigItem(
        "LLM",
        "Gemini_API_Base",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    chatglm_model = ConfigItem("LLM", "ChatGLM_Model", "glm-4")
    chatglm_api_key = ConfigItem("LLM", "ChatGLM_API_Key", "")
    chatglm_api_base = ConfigItem(
        "LLM", "ChatGLM_API_Base", "https://open.bigmodel.cn/api/paas/v4"
    )

    # 公益模型
    qwen_model = ConfigItem("LLM", "Qwen_Model", "qwen-plus")
    qwen_api_key = ConfigItem("LLM", "Qwen_API_Key", "")
    qwen_api_base = ConfigItem(
        "LLM", "Qwen_API_Base", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    qwen_enable_thinking = ConfigItem(
        "LLM", "Qwen_Enable_Thinking", True, BoolValidator()
    )

    public_model = ConfigItem("LLM", "Public_Model", "gpt-4o-mini")
    public_api_key = ConfigItem(
        "LLM", "Public_API_Key", "please-do-not-use-for-personal-purposes"
    )
    public_api_base = ConfigItem("LLM", "Public_API_Base", "https://ddg.bkfeng.top/v1")
    llm_request_timeout = RangeConfigItem(
        "LLM", "RequestTimeout", 300, RangeValidator(30, 900)
    )
    llm_cache_enabled = ConfigItem("LLM", "CacheEnabled", True, BoolValidator())
    llm_batch_context_enabled = ConfigItem(
        "LLM", "BatchContextEnabled", True, BoolValidator()
    )
    llm_batch_context_max_chars = RangeConfigItem(
        "LLM", "BatchContextMaxChars", 300, RangeValidator(0, 1000)
    )

    # ------------------- 翻译配置 -------------------
    translator_service = OptionsConfigItem(
        "Translate",
        "TranslatorServiceEnum",
        TranslatorServiceEnum.BING,
        OptionsValidator(TranslatorServiceEnum),
        EnumSerializer(TranslatorServiceEnum),
    )
    need_reflect_translate = ConfigItem(
        "Translate", "NeedReflectTranslate", False, BoolValidator()
    )
    deeplx_endpoint = ConfigItem("Translate", "DeeplxEndpoint", "")
    batch_size = RangeConfigItem("Translate", "BatchSize", 10, RangeValidator(5, 30))
    thread_num = RangeConfigItem("Translate", "ThreadNum", 10, RangeValidator(1, 100))
    translation_max_length = RangeConfigItem(
        "Translate", "TranslationMaxLength", 0, RangeValidator(0, 80)
    )

    # ------------------- 转录配置 -------------------
    transcribe_model = OptionsConfigItem(
        "Transcribe",
        "TranscribeModel",
        TranscribeModelEnum.BIJIAN,
        OptionsValidator(TranscribeModelEnum),
        EnumSerializer(TranscribeModelEnum),
    )
    use_asr_cache = ConfigItem("Transcribe", "UseASRCache", True, BoolValidator())
    transcribe_language = OptionsConfigItem(
        "Transcribe",
        "TranscribeLanguage",
        TranscribeLanguageEnum.ENGLISH,
        OptionsValidator(TranscribeLanguageEnum),
        EnumSerializer(TranscribeLanguageEnum),
    )

    # ------------------- Whisper Cpp 配置 -------------------
    whisper_model = OptionsConfigItem(
        "Whisper",
        "WhisperModel",
        WhisperModelEnum.TINY,
        OptionsValidator(WhisperModelEnum),
        EnumSerializer(WhisperModelEnum),
    )

    # ------------------- Faster Whisper 配置 -------------------
    faster_whisper_program = ConfigItem(
        "FasterWhisper",
        "Program",
        "faster-whisper-xxl.exe",
    )
    faster_whisper_model = OptionsConfigItem(
        "FasterWhisper",
        "Model",
        FasterWhisperModelEnum.TINY,
        OptionsValidator(FasterWhisperModelEnum),
        EnumSerializer(FasterWhisperModelEnum),
    )
    faster_whisper_model_dir = ConfigItem("FasterWhisper", "ModelDir", "")
    faster_whisper_device = OptionsConfigItem(
        "FasterWhisper", "Device", "cuda", OptionsValidator(["cuda", "cpu"])
    )
    # VAD 参数
    faster_whisper_vad_filter = ConfigItem(
        "FasterWhisper", "VadFilter", True, BoolValidator()
    )
    faster_whisper_vad_threshold = RangeConfigItem(
        "FasterWhisper", "VadThreshold", 0.4, RangeValidator(0, 1)
    )
    faster_whisper_vad_method = OptionsConfigItem(
        "FasterWhisper",
        "VadMethod",
        VadMethodEnum.SILERO_V4,
        OptionsValidator(VadMethodEnum),
        EnumSerializer(VadMethodEnum),
    )
    # 人声提取
    faster_whisper_ff_mdx_kim2 = ConfigItem(
        "FasterWhisper", "FfMdxKim2", False, BoolValidator()
    )
    # 文本处理参数
    faster_whisper_one_word = ConfigItem(
        "FasterWhisper", "OneWord", True, BoolValidator()
    )
    # 提示词
    faster_whisper_prompt = ConfigItem("FasterWhisper", "Prompt", "")

    # ------------------- WhisperX 配置 -------------------
    whisperx_model = ConfigItem("WhisperX", "Model", "large-v3")
    whisperx_device = OptionsConfigItem(
        "WhisperX", "Device", "cuda", OptionsValidator(["cuda", "cpu"])
    )
    whisperx_compute_type = ConfigItem("WhisperX", "ComputeType", "float16")
    whisperx_batch_size = RangeConfigItem(
        "WhisperX", "BatchSize", 8, RangeValidator(1, 32)
    )
    whisperx_auto_language = ConfigItem(
        "WhisperX", "AutoLanguage", False, BoolValidator()
    )
    whisperx_hotwords = ConfigItem("WhisperX", "Hotwords", "")
    whisperx_initial_prompt = ConfigItem("WhisperX", "InitialPrompt", "")
    whisperx_vad_method = OptionsConfigItem(
        "WhisperX",
        "VadMethod",
        "silero",
        OptionsValidator(["silero", "pyannote"]),
    )
    whisperx_vad_threshold = ConfigItem("WhisperX", "VadThreshold", 0.5)
    whisperx_local_silero_dir = ConfigItem(
        "WhisperX",
        "LocalSileroDir",
        str(MODEL_PATH / "silero-vad"),
    )
    whisperx_word_timestamps = ConfigItem(
        "WhisperX", "WordTimestamps", False, BoolValidator()
    )
    whisperx_align = ConfigItem("WhisperX", "Align", True, BoolValidator())
    # ------------------- Whisper API 配置 -------------------
    whisper_api_base = ConfigItem("WhisperAPI", "WhisperApiBase", "")
    whisper_api_key = ConfigItem("WhisperAPI", "WhisperApiKey", "")
    whisper_api_model = OptionsConfigItem("WhisperAPI", "WhisperApiModel", "")
    whisper_api_prompt = ConfigItem("WhisperAPI", "WhisperApiPrompt", "")

    # ------------------- 字幕配置 -------------------
    need_optimize = ConfigItem("Subtitle", "NeedOptimize", False, BoolValidator())
    need_translate = ConfigItem("Subtitle", "NeedTranslate", False, BoolValidator())
    need_split = ConfigItem("Subtitle", "NeedSplit", False, BoolValidator())
    split_type = OptionsConfigItem(
        "Subtitle",
        "SplitType",
        SplitTypeEnum.SENTENCE,
        OptionsValidator(SplitTypeEnum),
        EnumSerializer(SplitTypeEnum),
    )
    target_language = OptionsConfigItem(
        "Subtitle",
        "TargetLanguage",
        TargetLanguageEnum.CHINESE_SIMPLIFIED,
        OptionsValidator(TargetLanguageEnum),
        EnumSerializer(TargetLanguageEnum),
    )
    max_word_count_cjk = ConfigItem(
        "Subtitle", "MaxWordCountCJK", 25, RangeValidator(8, 100)
    )
    max_word_count_english = ConfigItem(
        "Subtitle", "MaxWordCountEnglish", 20, RangeValidator(8, 100)
    )
    needs_remove_translated_chinese_commas = ConfigItem(
        "Subtitle", "NeedsRemoveTranslatedChineseCommas", False, BoolValidator()
    )
    needs_remove_punctuation = ConfigItem(
        "Subtitle", "NeedsRemovePunctuation", True, BoolValidator()
    )
    custom_prompt_text = ConfigItem("Subtitle", "CustomPromptText", "")

    # ------------------- 提示词中心 -------------------
    prompt_split_semantic = ConfigItem("PromptCenter", "SplitSemantic", "")
    prompt_split_sentence = ConfigItem("PromptCenter", "SplitSentence", "")
    prompt_summarizer = ConfigItem("PromptCenter", "Summarizer", "")
    prompt_optimizer = ConfigItem("PromptCenter", "Optimizer", "")
    prompt_translate = ConfigItem("PromptCenter", "Translate", "")
    prompt_reflect_translate = ConfigItem("PromptCenter", "ReflectTranslate", "")
    prompt_single_translate = ConfigItem("PromptCenter", "SingleTranslate", "")

    # ------------------- 字幕样式配置 -------------------
    subtitle_style_name = ConfigItem("SubtitleStyle", "StyleName", "default")
    subtitle_layout = ConfigItem("SubtitleStyle", "Layout", "译文在上")
    subtitle_preview_image = ConfigItem("SubtitleStyle", "PreviewImage", "")

    # ------------------- 保存配置 -------------------
    work_dir = ConfigItem("Save", "Work_Dir", WORK_PATH, FolderValidator())

    # ------------------- 下载设置 -------------------
    download_center_output_dir = ConfigItem("Download", "CenterOutputDir", "")
    download_engine_strategy = OptionsConfigItem(
        "Download",
        "EngineStrategy",
        "智能选择",
        OptionsValidator(["单线程", "多线程", "智能选择"]),
    )
    download_auto_refresh_edge_cookies = ConfigItem(
        "Download", "AutoRefreshEdgeCookies", False, BoolValidator()
    )
    download_center_mode = OptionsConfigItem(
        "Download",
        "CenterMode",
        "simple",
        OptionsValidator(["simple", "professional"]),
    )
    download_center_simple_preset = OptionsConfigItem(
        "Download",
        "CenterSimplePreset",
        "best_quality",
        OptionsValidator(
            [
                "best_quality",
                "mp4_compatible",
                "pr_smart",
                "custom_preferences",
                "audio_only",
                "subtitle_only",
                "thumbnail_only",
            ]
        ),
    )
    download_center_professional_mode = OptionsConfigItem(
        "Download",
        "CenterProfessionalMode",
        "video_audio",
        OptionsValidator(["video_audio", "video", "audio"]),
    )
    download_center_need_subtitle = ConfigItem(
        "Download", "CenterNeedSubtitle", False, BoolValidator()
    )
    download_center_need_thumbnail = ConfigItem(
        "Download", "CenterNeedThumbnail", True, BoolValidator()
    )
    download_center_need_metadata = ConfigItem(
        "Download", "CenterNeedMetadata", False, BoolValidator()
    )
    download_center_need_description_txt = ConfigItem(
        "Download", "CenterNeedDescriptionTxt", True, BoolValidator()
    )
    download_center_subtitle_mode = OptionsConfigItem(
        "Download",
        "CenterSubtitleMode",
        "manual",
        OptionsValidator(["manual", "auto"]),
    )
    download_center_custom_video_codec = OptionsConfigItem(
        "Download",
        "CenterCustomVideoCodec",
        "auto",
        OptionsValidator(["auto", "avc1", "av01", "vp9"]),
    )
    download_center_custom_container = OptionsConfigItem(
        "Download",
        "CenterCustomContainer",
        "auto",
        OptionsValidator(["auto", "mp4", "webm"]),
    )
    download_center_custom_audio_codec = OptionsConfigItem(
        "Download",
        "CenterCustomAudioCodec",
        "auto",
        OptionsValidator(["auto", "mp4a", "opus"]),
    )
    download_center_pr_smart_postprocess = ConfigItem(
        "Download", "CenterPRSmartPostprocess", False, BoolValidator()
    )
    download_center_pr_smart_transcript_txt = ConfigItem(
        "Download", "CenterPRSmartTranscriptTxt", False, BoolValidator()
    )

    # ------------------- 软件页面配置 -------------------
    micaEnabled = ConfigItem("MainWindow", "MicaEnabled", False, BoolValidator())
    dpiScale = OptionsConfigItem(
        "MainWindow",
        "DpiScale",
        "Auto",
        OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]),
        restart=True,
    )
    language = OptionsConfigItem(
        "MainWindow",
        "Language",
        Language.AUTO,
        OptionsValidator(Language),
        LanguageSerializer(),
        restart=True,
    )

    # ------------------- 更新配置 -------------------
    checkUpdateAtStartUp = ConfigItem(
        "Update", "CheckUpdateAtStartUp", True, BoolValidator()
    )

    # ------------------- 下载代理配置 -------------------
    download_proxy_mode = OptionsConfigItem(
        "Download",
        "ProxyMode",
        "自动检测",
        OptionsValidator(["自动检测", "手动设置", "不使用代理"]),
    )
    download_proxy_url = ConfigItem(
        "Download",
        "ProxyURL",
        "http://127.0.0.1:7897",
    )


cfg = Config()
cfg.themeMode.value = Theme.DARK
cfg.themeColor.value = QColor("#ff28f08b")
qconfig.load(SETTINGS_PATH, cfg)
