from app.common.config import LEGACY_LANGUAGE_DISPLAY_NAMES, LegacyEnumSerializer, cfg
from app.core.entities import TargetLanguageEnum, TranscribeLanguageEnum


LANGUAGE_LABELS = {
    "中文",
    "英语",
    "法语",
    "俄语",
    "阿拉伯语",
    "西班牙语",
    "日本語",
    "德语",
    "韩语",
}


def test_target_language_options_are_limited_to_supported_languages():
    assert {language.value for language in TargetLanguageEnum} == LANGUAGE_LABELS
    assert {
        language.value for language in cfg.target_language.validator.options
    } == LANGUAGE_LABELS


def test_transcribe_language_options_are_limited_to_supported_languages():
    assert {language.value for language in TranscribeLanguageEnum} == LANGUAGE_LABELS
    assert {
        language.value for language in cfg.transcribe_language.validator.options
    } == LANGUAGE_LABELS


def test_legacy_language_values_fall_back_to_supported_options():
    target_serializer = LegacyEnumSerializer(
        TargetLanguageEnum,
        LEGACY_LANGUAGE_DISPLAY_NAMES,
        TargetLanguageEnum.CHINESE,
    )
    transcribe_serializer = LegacyEnumSerializer(
        TranscribeLanguageEnum,
        LEGACY_LANGUAGE_DISPLAY_NAMES,
        TranscribeLanguageEnum.ENGLISH,
    )

    assert target_serializer.deserialize("繁体中文") == TargetLanguageEnum.CHINESE
    assert target_serializer.deserialize("Japanese") == TargetLanguageEnum.JAPANESE
    assert transcribe_serializer.deserialize("日本語") == TranscribeLanguageEnum.JAPANESE
    assert transcribe_serializer.deserialize("German") == TranscribeLanguageEnum.GERMAN
    assert target_serializer.deserialize("Korean") == TargetLanguageEnum.KOREAN
