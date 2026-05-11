import hashlib
import math
from string import Template
from typing import Callable, Dict, Optional, List, Any, Union
import logging
from pathlib import Path
import os
import retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from abc import ABC, abstractmethod
from enum import Enum
from openai import OpenAI
import json
from dataclasses import dataclass
from functools import lru_cache
import signal
import requests
import re
import html
from urllib.parse import quote

from app.config import CACHE_PATH
from app.core.bk_asr.asr_data import ASRData, ASRDataSeg
from app.core.storage.cache_manager import CacheManager
from app.core.utils import json_repair
from app.core.subtitle_processor.prompt import (
    PROMPT_REFLECT_TRANSLATE,
    PROMPT_SINGLE_TRANSLATE,
    PROMPT_TRANSLATE,
    get_prompt_template,
)
from app.core.utils.logger import setup_logger
from app.core.utils.openai_compat import (
    extract_openai_usage,
    format_openai_compat_error,
    get_openai_compat_request_options,
)


logger = setup_logger("subtitle_translator")

TRANSLATION_READABILITY_POLICY_VERSION = 1
CJK_READING_CHARS_PER_SECOND = 12
NON_CJK_READING_WORDS_PER_SECOND = 3
MIN_CJK_READING_BUDGET = 18
MIN_NON_CJK_READING_BUDGET = 6


class TranslatorType(Enum):
    """翻译器类型"""

    OPENAI = "openai"
    GOOGLE = "google"
    BING = "bing"
    DEEPLX = "deeplx"


class BaseTranslator(ABC):
    """翻译器基类"""

    def __init__(
        self,
        thread_num: int = 10,
        batch_num: int = 20,
        target_language: str = "Chinese",
        retry_times: int = 1,
        timeout: int = 300,
        use_cache: bool = True,
        batch_context_enabled: bool = True,
        batch_context_max_chars: int = 300,
        update_callback: Optional[Callable] = None,
        custom_prompt: Optional[str] = None,
        usage_callback: Optional[Callable] = None,
    ):
        self.thread_num = thread_num
        self.batch_num = batch_num
        self.target_language = target_language
        self.retry_times = retry_times
        self.timeout = timeout
        self.use_cache = use_cache
        self.batch_context_enabled = batch_context_enabled
        self.batch_context_max_chars = max(0, int(batch_context_max_chars or 0))
        self.is_running = True
        self.update_callback = update_callback
        self.custom_prompt = custom_prompt
        self.usage_callback = usage_callback
        self.cache_manager = CacheManager(str(CACHE_PATH))
        self.executor = None

    def _init_thread_pool(self, task_count: int):
        """初始化线程池"""
        max_workers = max(1, min(int(self.thread_num or 1), max(1, task_count)))
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        import atexit

        atexit.register(self.stop)

    def translate_subtitle(self, subtitle_data: Union[str, ASRData]) -> ASRData:
        """翻译字幕文件"""
        try:
            # 读取字幕文件
            if isinstance(subtitle_data, str):
                asr_data = ASRData.from_subtitle_file(subtitle_data)
            else:
                asr_data = subtitle_data

            # 将ASRData转换为字典格式
            subtitle_dict = {
                str(i): seg.text for i, seg in enumerate(asr_data.segments, 1)
            }
            self._subtitle_timing_by_key = {
                str(i): {
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "duration_ms": max(0, seg.end_time - seg.start_time),
                }
                for i, seg in enumerate(asr_data.segments, 1)
            }

            # 分批处理字幕
            chunks = self._split_chunks(subtitle_dict)

            # 多线程翻译
            translated_dict = self._parallel_translate(chunks)

            # 创建新的ASRDataSeg列表
            new_segments = self._create_segments(asr_data.segments, translated_dict)

            return ASRData(new_segments)
        except Exception as e:
            logger.error(f"翻译失败：{str(e)}")
            raise RuntimeError(f"翻译失败：{str(e)}")

    def _split_chunks(self, subtitle_dict: Dict[str, str]) -> List[Dict[str, str]]:
        """将字幕分割成块"""
        items = list(subtitle_dict.items())
        return [
            dict(items[i : i + self.batch_num])
            for i in range(0, len(items), self.batch_num)
        ]

    @staticmethod
    def _build_chunk_context(
        chunks: List[Dict[str, str]],
        index: int,
        max_lines: int = 6,
        max_chars: int = 600,
    ) -> str:
        """构建当前批次前文参考，降低后续批次语义漂移"""
        if index <= 0 or max_chars <= 0:
            return ""

        previous_lines = list(chunks[index - 1].values())[-max_lines:]
        context = "\n".join(previous_lines).strip()
        if len(context) > max_chars:
            context = context[-max_chars:]
        return context

    def _parallel_translate(self, chunks: List[Dict[str, str]]) -> Dict[str, str]:
        """并行翻译所有块"""
        if not chunks:
            return {}
        self._init_thread_pool(len(chunks))
        futures = {}
        translated_dict = {}
        pending_results = {}
        next_chunk_index = 0

        for index, chunk in enumerate(chunks):
            context_before = (
                self._build_chunk_context(
                    chunks, index, max_chars=self.batch_context_max_chars
                )
                if self.batch_context_enabled
                else ""
            )
            future = self.executor.submit(
                self._safe_translate_chunk, chunk, context_before
            )
            futures[future] = (index, chunk)

        for future in as_completed(futures):
            if not self.is_running:
                logger.info("翻译器已停止运行，退出翻译")
                break
            index, chunk = futures[future]
            try:
                result = future.result()
                pending_results[index] = result
            except Exception as e:
                logger.error(f"翻译块失败：{str(e)}")
                pending_results[index] = {
                    k: f"{v}||ERROR" for k, v in chunk.items()
                }

            while next_chunk_index in pending_results:
                result = pending_results.pop(next_chunk_index)
                translated_dict.update(result)
                if self.update_callback:
                    self.update_callback(result)
                next_chunk_index += 1

        return translated_dict

    def _safe_translate_chunk(
        self, chunk: Dict[str, str], context_before: str = ""
    ) -> Dict[str, str]:
        """安全的翻译块，包含重试逻辑"""
        for i in range(self.retry_times):
            try:
                return self._translate_chunk(chunk, context_before=context_before)
            except Exception as e:
                if i == self.retry_times - 1:
                    raise
                logger.warning(
                    f"翻译重试 {i+1}/{self.retry_times}: {format_openai_compat_error(e, model_name=getattr(self, 'model', None))}"
                )

    @staticmethod
    def _create_segments(
        original_segments: List[ASRDataSeg], translated_dict: Dict[str, str]
    ) -> List[ASRDataSeg]:
        """创建新的字幕段"""
        for i, seg in enumerate(original_segments, 1):
            try:
                seg.translated_text = translated_dict[str(i)]  # 设置翻译文本
            except Exception as e:
                logger.error(f"创建新的字幕段失败：{str(e)}")
                seg.translated_text = seg.text
        return original_segments

    @abstractmethod
    def _translate_chunk(
        self, subtitle_chunk: Dict[str, str], context_before: str = ""
    ) -> Dict[str, str]:
        """翻译字幕块"""
        pass

    def stop(self):
        """停止翻译器"""
        if not self.is_running:
            return

        logger.info("正在停止翻译器...")
        self.is_running = False
        if hasattr(self, "executor") and self.executor is not None:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                logger.error(f"关闭线程池时出错：{str(e)}")
            finally:
                self.executor = None


class OpenAITranslator(BaseTranslator):
    """OpenAI翻译器"""

    def __init__(
        self,
        thread_num: int = 10,
        batch_num: int = 20,
        target_language: str = "Chinese",
        model: str = "gpt-4o-mini",
        custom_prompt: str = "",
        is_reflect: bool = False,
        temperature: float = 0.7,
        timeout: int = 300,
        retry_times: int = 1,
        translation_max_length: int = 0,
        use_cache: bool = True,
        batch_context_enabled: bool = True,
        batch_context_max_chars: int = 300,
        update_callback: Optional[Callable] = None,
        usage_callback: Optional[Callable] = None,
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            retry_times=retry_times,
            timeout=timeout,
            use_cache=use_cache,
            batch_context_enabled=batch_context_enabled,
            batch_context_max_chars=batch_context_max_chars,
            update_callback=update_callback,
            usage_callback=usage_callback,
        )

        self._init_client()
        self.model = model
        self.custom_prompt = custom_prompt
        self.is_reflect = is_reflect
        self.temperature = temperature
        self.translation_max_length = max(0, int(translation_max_length or 0))

    def _init_client(self):
        """初始化OpenAI客户端"""
        base_url = os.getenv("OPENAI_BASE_URL")
        api_key = os.getenv("OPENAI_API_KEY")
        if not (base_url and api_key):
            raise ValueError("环境变量 OPENAI_BASE_URL 和 OPENAI_API_KEY 必须设置")

        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def _get_translate_prompt(self) -> str:
        """获取翻译提示词"""
        prompt = get_prompt_template(
            PROMPT_REFLECT_TRANSLATE if self.is_reflect else PROMPT_TRANSLATE
        )
        return Template(prompt).safe_substitute(
            target_language=self.target_language,
            custom_prompt=self.custom_prompt,
            translation_length_instruction=self._get_length_instruction(),
        )

    def _get_length_instruction(self) -> str:
        if self.translation_max_length <= 0:
            return (
                "\n# 字幕翻译优先级:\n"
                "- 完整准确 > 阅读流畅 > 简短凝练。\n"
                "- 不要把翻译改写成摘要；不得省略否定、数字、时间、条件、因果、专有名词、动作对象或术语。\n"
                "- 如果译文较长，优先使用自然、完整的表达，必要时可在译文内部使用换行，而不是删除信息。\n"
            )
        return (
            "\n# 字幕阅读速度建议:\n"
            "- 完整准确 > 阅读流畅 > 简短凝练。\n"
            "- 不要把翻译改写成摘要；不得省略否定、数字、时间、条件、因果、专有名词、动作对象或术语。\n"
            f"- 译文长度建议以 {self.translation_max_length} 作为基础参考，并结合每条字幕时长动态调整。\n"
            "- 长度建议是软约束；如果压缩会丢失信息，可以超过建议长度。\n"
            "- 如果译文较长，优先使用自然、完整的表达，必要时可在译文内部使用换行，而不是删除信息。\n"
        )

    def _is_cjk_target_language(self) -> bool:
        language = str(self.target_language or "").lower()
        cjk_markers = (
            "中文",
            "简体",
            "繁体",
            "漢",
            "汉",
            "日本",
            "日语",
            "韓",
            "韩",
            "粤",
            "粵",
            "chinese",
            "japanese",
            "korean",
            "cantonese",
            "zh",
            "ja",
            "ko",
            "yue",
        )
        return any(marker in language for marker in cjk_markers)

    def _build_reading_budget(self, subtitle_key: str) -> Optional[Dict[str, Any]]:
        timing = getattr(self, "_subtitle_timing_by_key", {}).get(str(subtitle_key))
        if not timing:
            return None

        duration_ms = max(0, int(timing.get("duration_ms", 0)))
        duration_seconds = duration_ms / 1000
        is_cjk = self._is_cjk_target_language()
        budget: Dict[str, Any] = {
            "duration_seconds": duration_seconds,
            "unit": "字" if is_cjk else "词",
            "suggested_length": None,
        }

        if self.translation_max_length <= 0:
            return budget

        if is_cjk:
            dynamic_budget = math.ceil(duration_seconds * CJK_READING_CHARS_PER_SECOND)
            minimum = MIN_CJK_READING_BUDGET
        else:
            dynamic_budget = math.ceil(
                duration_seconds * NON_CJK_READING_WORDS_PER_SECOND
            )
            minimum = MIN_NON_CJK_READING_BUDGET

        budget["suggested_length"] = max(
            minimum,
            int(self.translation_max_length),
            dynamic_budget,
        )
        return budget

    def _build_timing_instruction(self, subtitle_chunk: Dict[str, str]) -> str:
        lines = []
        for key in subtitle_chunk:
            budget = self._build_reading_budget(key)
            if not budget:
                continue
            if budget["suggested_length"] is None:
                lines.append(
                    f"{key}: duration={budget['duration_seconds']:.2f}s, no length target"
                )
            else:
                lines.append(
                    f"{key}: duration={budget['duration_seconds']:.2f}s, "
                    f"suggested_length≈{budget['suggested_length']}{budget['unit']}"
                )

        if not lines:
            return ""

        return (
            "Read-only timing and readability reference for the subtitles below. "
            "Use it only as a soft readability guide. Completeness and accuracy "
            "take priority over these suggestions. Do not output this block.\n"
            "<subtitle_timing>\n"
            + "\n".join(lines)
            + "\n</subtitle_timing>\n\n"
        )

    @staticmethod
    def _count_text_units(text: str) -> int:
        cjk_chars = re.findall(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", text)
        words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)
        return len(cjk_chars) + len(words)

    @staticmethod
    def _extract_numbers(text: str) -> List[str]:
        return re.findall(r"\d+(?:[.,:%:/-]\d+)*%?", text or "")

    @staticmethod
    def _extract_proper_terms(text: str) -> List[str]:
        terms = []
        common_words = {
            "A",
            "An",
            "And",
            "But",
            "For",
            "I",
            "If",
            "It",
            "So",
            "The",
            "This",
            "That",
            "We",
            "You",
        }
        source = text or ""
        first_text_index = len(source) - len(source.lstrip())
        for match in re.finditer(r"\b[A-Z][A-Za-z0-9._+-]{1,}\b", source):
            term = match.group(0)
            if term in common_words:
                continue
            if match.start() == first_text_index and not term.isupper():
                continue
            terms.append(term)
        return sorted(set(terms))

    @staticmethod
    def _has_source_negation(text: str) -> bool:
        return bool(
            re.search(
                r"\b(?:not|no|never|cannot|can't|don't|doesn't|didn't|without|won't|isn't|aren't|n't)\b|不|未|无|沒|没|不能|不会|不要",
                text or "",
                flags=re.IGNORECASE,
            )
        )

    @staticmethod
    def _has_target_negation(text: str) -> bool:
        return bool(
            re.search(
                r"\b(?:not|no|never|cannot|can't|without|won't|isn't|aren't|n't)\b|不|未|无|沒|没|非|勿|别|不能|不会|不要",
                text or "",
                flags=re.IGNORECASE,
            )
        )

    def _extract_custom_prompt_terms(self) -> List[str]:
        prompt = self.custom_prompt or ""
        terms = re.findall(r"[`'\"“”‘’]([^`'\"“”‘’]{2,40})[`'\"“”‘’]", prompt)
        terms.extend(
            re.findall(
                r"^\s*[-*]?\s*([A-Za-z][A-Za-z0-9._ +/#-]{1,40})\s*(?:=|->|:|：)",
                prompt,
                flags=re.MULTILINE,
            )
        )
        return sorted({term.strip() for term in terms if term.strip()})

    def _find_suspicious_compressions(
        self, subtitle_chunk: Dict[str, str], translated_dict: Dict[str, str]
    ) -> Dict[str, List[str]]:
        suspicious = {}
        custom_terms = self._extract_custom_prompt_terms()

        for key, source_text in subtitle_chunk.items():
            translated_text = str(translated_dict.get(key, "") or "")
            reasons = []
            source_units = self._count_text_units(source_text)
            translated_units = self._count_text_units(translated_text)

            if source_units >= 8 and translated_units <= max(4, int(source_units * 0.35)):
                reasons.append("translated text is much shorter than the source")

            normalized_translation = translated_text.lower()
            missing_numbers = [
                number
                for number in self._extract_numbers(source_text)
                if number and number not in translated_text
            ]
            if missing_numbers:
                reasons.append("numbers may be missing: " + ", ".join(missing_numbers))

            missing_terms = [
                term
                for term in self._extract_proper_terms(source_text)
                if term.lower() not in normalized_translation
            ]
            if missing_terms:
                reasons.append("proper nouns may be missing: " + ", ".join(missing_terms))

            custom_prompt_terms = [
                term
                for term in custom_terms
                if term in source_text and term.lower() not in normalized_translation
            ]
            if custom_prompt_terms:
                reasons.append(
                    "custom prompt terms may be missing: "
                    + ", ".join(custom_prompt_terms)
                )

            if self._has_source_negation(source_text) and not self._has_target_negation(
                translated_text
            ):
                reasons.append("source negation may be missing")

            if reasons:
                suspicious[key] = reasons

        return suspicious

    def _translate_chunk(
        self, subtitle_chunk: Dict[str, str], context_before: str = ""
    ) -> Dict[str, str]:
        """翻译字幕块"""
        logger.info(
            f"[+]正在翻译字幕：{next(iter(subtitle_chunk))} - {next(reversed(subtitle_chunk))}"
        )

        # 获取提示词
        prompt = self._get_translate_prompt()
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        timing_instruction = self._build_timing_instruction(subtitle_chunk)
        timing_instruction_hash = hashlib.md5(
            timing_instruction.encode()
        ).hexdigest()

        try:
            # 检查缓存
            cache_params = {
                "target_language": self.target_language,
                "is_reflect": self.is_reflect,
                "temperature": self.temperature,
                "prompt_hash": prompt_hash,
                "context_before": context_before,
                "batch_context_enabled": self.batch_context_enabled,
                "batch_context_max_chars": self.batch_context_max_chars,
                "translation_max_length": self.translation_max_length,
                "translation_readability_policy_version": TRANSLATION_READABILITY_POLICY_VERSION,
                "timing_instruction_hash": timing_instruction_hash,
            }
            cache_key = json.dumps(subtitle_chunk, ensure_ascii=False)
            cache_result = (
                self.cache_manager.get_llm_result(
                    prompt=cache_key,
                    model_name=self.model,
                    **cache_params,
                )
                if self.use_cache
                else None
            )

            result = {}
            if cache_result:
                result = json.loads(cache_result)
            else:
                user_content = json.dumps(subtitle_chunk, ensure_ascii=False)
                if timing_instruction:
                    user_content = timing_instruction + user_content
                if context_before:
                    user_content = (
                        "Reference context from the immediately preceding subtitles. "
                        "Use it only to keep terminology and style consistent. "
                        "Do not translate or output this context.\n"
                        f"<context>{context_before}</context>\n\n"
                        f"{user_content}"
                    )
                # 调用API翻译
                response = self._call_api(prompt, user_content)
                if self.usage_callback:
                    self.usage_callback("translate", extract_openai_usage(response))
                # 解析结果
                result = self._normalize_batch_result(
                    json_repair.loads(response.choices[0].message.content),
                    subtitle_chunk,
                )
                if result is None:
                    logger.warning(f"翻译结果数量不匹配，将使用单条翻译模式重试")
                    return self._translate_chunk_single(subtitle_chunk, context_before)
                # 保存到缓存
                if self.use_cache:
                    self.cache_manager.set_llm_result(
                        prompt=cache_key,
                        result=json.dumps(result, ensure_ascii=False),
                        model_name=self.model,
                        **cache_params,
                    )

            if self.is_reflect:
                result = {k: f"{v['revised_translation']}" for k, v in result.items()}
            else:
                result = {k: f"{v}" for k, v in result.items()}

            suspicious = self._find_suspicious_compressions(subtitle_chunk, result)
            if suspicious:
                logger.info(
                    "检测到疑似过度缩句，正在单条重译: %s",
                    ", ".join(suspicious.keys()),
                )
                retry_chunk = {key: subtitle_chunk[key] for key in suspicious}
                retry_result = self._translate_chunk_single(
                    retry_chunk,
                    context_before=context_before,
                    extra_instruction=(
                        "The previous translation looked like it may have omitted "
                        "important information. Translate fully and faithfully. "
                        "Do not summarize, and keep numbers, negation, named entities, "
                        "conditions, causal relations, actions, objects, and terms."
                    ),
                )
                for key, translated_text in retry_result.items():
                    if translated_text and translated_text != "ERROR":
                        result[key] = translated_text
                if self.use_cache and not self.is_reflect:
                    self.cache_manager.set_llm_result(
                        prompt=cache_key,
                        result=json.dumps(result, ensure_ascii=False),
                        model_name=self.model,
                        **cache_params,
                    )

            return result
        except Exception as e:
            try:
                return self._translate_chunk_single(subtitle_chunk, context_before)
            except Exception as e:
                formatted_error = format_openai_compat_error(
                    e, model_name=getattr(self, "model", None)
                )
                logger.error(f"翻译失败：{formatted_error}")
                raise RuntimeError(f"OpenAI API调用失败：{formatted_error}")

    @staticmethod
    def _normalize_batch_result(
        result: Any, subtitle_chunk: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(result, dict) or len(result) != len(subtitle_chunk):
            return None

        expected_keys = list(subtitle_chunk.keys())
        if all(key in result for key in expected_keys):
            return {key: result[key] for key in expected_keys}

        return {
            key: value
            for key, value in zip(expected_keys, result.values())
        }

    def _translate_chunk_single(
        self,
        subtitle_chunk: Dict[str, str],
        context_before: str = "",
        extra_instruction: str = "",
    ) -> Dict[str, str]:
        """单条翻译模式"""
        result = {}
        single_prompt = Template(
            get_prompt_template(PROMPT_SINGLE_TRANSLATE)
        ).safe_substitute(
            target_language=self.target_language,
            translation_length_instruction=self._get_length_instruction(),
        )
        prompt_hash = hashlib.md5(single_prompt.encode()).hexdigest()
        extra_instruction_hash = hashlib.md5(
            (extra_instruction or "").encode()
        ).hexdigest()
        for idx, text in subtitle_chunk.items():
            try:
                timing_instruction = self._build_timing_instruction({idx: text})
                timing_instruction_hash = hashlib.md5(
                    timing_instruction.encode()
                ).hexdigest()
                # 检查缓存
                cache_params = {
                    "target_language": self.target_language,
                    "is_reflect": self.is_reflect,
                    "temperature": self.temperature,
                    "prompt_hash": prompt_hash,
                    "context_before": context_before,
                    "batch_context_enabled": self.batch_context_enabled,
                    "batch_context_max_chars": self.batch_context_max_chars,
                    "translation_max_length": self.translation_max_length,
                    "model": self.model,
                    "translation_readability_policy_version": TRANSLATION_READABILITY_POLICY_VERSION,
                    "timing_instruction_hash": timing_instruction_hash,
                    "compression_retry": bool(extra_instruction),
                    "extra_instruction_hash": extra_instruction_hash,
                }
                cache_result = (
                    self.cache_manager.get_translation(
                        text,
                        "llm",
                        **cache_params,
                    )
                    if self.use_cache
                    else None
                )

                if cache_result:
                    result[idx] = cache_result
                    continue

                user_content = text
                if extra_instruction:
                    user_content = extra_instruction + "\n\n" + user_content
                if timing_instruction:
                    user_content = timing_instruction + user_content
                if context_before:
                    user_content = (
                        "Reference context from the immediately preceding subtitles. "
                        "Use it only to keep terminology and style consistent. "
                        "Do not translate or output this context.\n"
                        f"<context>{context_before}</context>\n\n"
                        f"{text}"
                    )
                response = self._call_api(single_prompt, user_content)
                if self.usage_callback:
                    self.usage_callback("translate", extract_openai_usage(response))
                translated_text = response.choices[0].message.content.strip()

                # 删除 DeepSeek-R1 等推理模型的思考过程 #300
                translated_text = re.sub(
                    r"<think>.*?</think>", "", translated_text, flags=re.DOTALL
                )
                translated_text = translated_text.strip()

                # 保存到缓存
                if self.use_cache:
                    self.cache_manager.set_translation(
                        text,
                        translated_text,
                        "llm",
                        **cache_params,
                    )

                result[idx] = translated_text
            except Exception as e:
                logger.error(
                    f"单条翻译失败 {idx}: {format_openai_compat_error(e, model_name=self.model)}"
                )
                result[idx] = "ERROR"  # 如果翻译失败，返回错误标记

        return result

    def _call_api(self, prompt: str, user_content: str) -> Any:
        """调用OpenAI API"""
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]

        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            **get_openai_compat_request_options(
                model_name=self.model, default_timeout=self.timeout
            ),
        )

    def _parse_response(self, response: Any) -> Dict[str, str]:
        """解析API响应"""
        try:
            result = json_repair.loads(response.choices[0].message.content)
            if self.is_reflect:
                return {k: v["revised_translation"] for k, v in result.items()}
            return result
        except Exception as e:
            raise ValueError(f"解析翻译结果失败：{str(e)}")


class GoogleTranslator(BaseTranslator):
    """谷歌翻译器"""

    def __init__(
        self,
        thread_num: int = 10,
        batch_num: int = 20,
        target_language: str = "Chinese",
        retry_times: int = 1,
        timeout: int = 20,
        use_cache: bool = True,
        batch_context_enabled: bool = True,
        batch_context_max_chars: int = 300,
        update_callback: Optional[Callable] = None,
        usage_callback: Optional[Callable] = None,
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            retry_times=retry_times,
            timeout=timeout,
            use_cache=use_cache,
            batch_context_enabled=batch_context_enabled,
            batch_context_max_chars=batch_context_max_chars,
            update_callback=update_callback,
            usage_callback=usage_callback,
        )
        self.session = requests.Session()
        self.endpoint = "http://translate.google.com/m"
        self.headers = {
            "User-Agent": "Mozilla/4.0 (compatible;MSIE 6.0;Windows NT 5.1;SV1;.NET CLR 1.1.4322;.NET CLR 2.0.50727;.NET CLR 3.0.04506.30)"
        }
        self.lang_map = {
            "简体中文": "zh-CN",
            "繁体中文": "zh-TW",
            "英语": "en",
            "日本語": "ja",
            "韩语": "ko",
            "粤语": "yue",
            "法语": "fr",
            "德语": "de",
            "西班牙语": "es",
            "俄语": "ru",
            "葡萄牙语": "pt",
            "土耳其语": "tr",
        }

    def _translate_chunk(
        self, subtitle_chunk: Dict[str, str], context_before: str = ""
    ) -> Dict[str, str]:
        """翻译字幕块"""
        result = {}
        if self.target_language in self.lang_map.values():
            target_lang = self.target_language
        else:
            target_lang = self.lang_map.get(self.target_language, "zh-CN")

        for idx, text in subtitle_chunk.items():
            try:
                # 检查缓存
                cache_params = {"target_language": target_lang}
                cache_result = (
                    self.cache_manager.get_translation(
                        text,
                        "google",
                        **cache_params,
                    )
                    if self.use_cache
                    else None
                )

                if cache_result:
                    result[idx] = cache_result
                    logger.info(f"使用缓存的Google翻译结果：{idx}")
                    continue

                text = text[:5000]  # google translate max length
                response = self.session.get(
                    self.endpoint,
                    params={"tl": target_lang, "sl": "auto", "q": text},
                    headers=self.headers,
                    timeout=self.timeout,
                )

                if response.status_code == 400:
                    result[idx] = "TRANSLATION ERROR"
                    continue

                response.raise_for_status()
                re_result = re.findall(
                    r'(?s)class="(?:t0|result-container)">(.*?)<', response.text
                )
                if re_result:
                    translated_text = html.unescape(re_result[0])
                    # 保存到缓存
                    if self.use_cache:
                        self.cache_manager.set_translation(
                            text,
                            translated_text,
                            "google",
                            **cache_params,
                        )
                    result[idx] = translated_text
                else:
                    result[idx] = "ERROR"
                    logger.warning(f"无法从Google翻译响应中提取翻译结果: {idx}")
            except Exception as e:
                logger.error(f"Google翻译失败 {idx}: {str(e)}")
                result[idx] = "ERROR"
        return result


class BingTranslator(BaseTranslator):
    """必应翻译器"""

    def __init__(
        self,
        thread_num: int = 10,
        batch_num: int = 20,
        target_language: str = "Chinese",
        retry_times: int = 1,
        timeout: int = 20,
        use_cache: bool = True,
        batch_context_enabled: bool = True,
        batch_context_max_chars: int = 300,
        update_callback: Optional[Callable] = None,
        usage_callback: Optional[Callable] = None,
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            retry_times=retry_times,
            timeout=timeout,
            use_cache=use_cache,
            batch_context_enabled=batch_context_enabled,
            batch_context_max_chars=batch_context_max_chars,
            update_callback=update_callback,
            usage_callback=usage_callback,
        )
        self.session = requests.Session()
        self.auth_endpoint = "https://edge.microsoft.com/translate/auth"
        self.translate_endpoint = (
            "https://api-edge.cognitive.microsofttranslator.com/translate"
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        }
        self.lang_map = {
            "简体中文": "zh-Hans",
            "繁体中文": "zh-Hant",
            "英语": "en",
            "日本語": "ja",
            "韩语": "ko",
            "粤语": "yue",
            "法语": "fr",
            "德语": "de",
            "西班牙语": "es",
            "俄语": "ru",
            "葡萄牙语": "pt",
            "土耳其语": "tr",
            "Chinese": "zh-Hans",
            "English": "en",
            "Japanese": "ja",
            "Korean": "ko",
            "French": "fr",
            "German": "de",
            "Russian": "ru",
            "Spanish": "es",
        }
        self._init_session()

    def _init_session(self):
        """初始化会话，获取必要的token"""
        try:
            response = self.session.get(self.auth_endpoint, timeout=self.timeout)
            response.raise_for_status()
            self.auth_token = response.text
            self.headers["authorization"] = f"Bearer {self.auth_token}"
        except Exception as e:
            logger.error(f"初始化必应翻译会话失败: {str(e)}")
            raise RuntimeError(f"初始化必应翻译会话失败: {str(e)}")

    def _translate_chunk(
        self, subtitle_chunk: Dict[str, str], context_before: str = ""
    ) -> Dict[str, str]:
        """翻译字幕块"""
        result = {}
        if self.target_language in self.lang_map.values():
            target_lang = self.target_language
        else:
            target_lang = self.lang_map.get(self.target_language, "zh-Hans")

        # 准备批量翻译的数据
        texts_to_translate = []
        idx_map = []

        for idx, text in subtitle_chunk.items():
            # 检查缓存
            cache_params = {"target_language": target_lang}
            original_text = text[:5000]
            cache_result = (
                self.cache_manager.get_translation(
                    original_text,
                    "bing",
                    **cache_params,
                )
                if self.use_cache
                else None
            )

            if cache_result:
                result[idx] = cache_result
                logger.debug(f"使用缓存的Bing翻译结果：{idx}")
            else:
                texts_to_translate.append({"Text": original_text})  # 限制文本长度
                idx_map.append(idx)

        if texts_to_translate:
            try:
                params = {
                    "to": target_lang,
                    "api-version": "3.0",
                    "includeSentenceLength": "true",
                }

                response = self.session.post(
                    self.translate_endpoint,
                    params=params,
                    headers=self.headers,
                    json=texts_to_translate,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                translations = response.json()

                # 处理翻译结果
                for i, translation in enumerate(translations):
                    idx = idx_map[i]
                    translated_text = translation["translations"][0]["text"]

                    # 保存到缓存
                    original_text = texts_to_translate[i]["Text"]
                    if self.use_cache:
                        self.cache_manager.set_translation(
                            original_text,
                            translated_text,
                            "bing",
                            **cache_params,
                        )

                    result[idx] = translated_text

            except Exception as e:
                logger.error(f"必应翻译失败: {str(e)}")
                # 如果是token过期，尝试重新初始化会话
                if "token" in str(e).lower() or response.status_code in [401, 403]:
                    try:
                        self._init_session()
                    except Exception as e:
                        logger.error(f"重新初始化必应翻译会话失败: {str(e)}")
                # 对于失败的翻译，标记为错误
                for idx in idx_map:
                    if idx not in result:
                        result[idx] = "ERROR"

        return result


class DeepLXTranslator(BaseTranslator):
    """DeepLX翻译器"""

    def __init__(
        self,
        thread_num: int = 10,
        batch_num: int = 20,
        target_language: str = "Chinese",
        retry_times: int = 1,
        timeout: int = 20,
        use_cache: bool = True,
        batch_context_enabled: bool = True,
        batch_context_max_chars: int = 300,
        update_callback: Optional[Callable] = None,
        usage_callback: Optional[Callable] = None,
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            retry_times=retry_times,
            timeout=timeout,
            use_cache=use_cache,
            batch_context_enabled=batch_context_enabled,
            batch_context_max_chars=batch_context_max_chars,
            update_callback=update_callback,
            usage_callback=usage_callback,
        )
        self.session = requests.Session()
        self.endpoint = os.getenv("DEEPLX_ENDPOINT", "https://api.deeplx.org/translate")
        self.lang_map = {
            "简体中文": "zh",
            "繁体中文": "zh-TW",
            "英语": "en",
            "日本語": "ja",
            "韩语": "ko",
            "法语": "fr",
            "德语": "de",
            "西班牙语": "es",
            "俄语": "ru",
            "葡萄牙语": "pt",
            "土耳其语": "tr",
            "Chinese": "zh",
            "English": "en",
            "Japanese": "ja",
            "Korean": "ko",
            "French": "fr",
            "German": "de",
            "Spanish": "es",
            "Russian": "ru",
        }

    def _translate_chunk(
        self, subtitle_chunk: Dict[str, str], context_before: str = ""
    ) -> Dict[str, str]:
        """翻译字幕块"""
        result = {}
        if self.target_language in self.lang_map.values():
            target_lang = self.target_language
        else:
            target_lang = self.lang_map.get(self.target_language, "zh").lower()

        for idx, text in subtitle_chunk.items():
            try:
                # 检查缓存
                cache_params = {
                    "target_language": target_lang,
                    "endpoint": self.endpoint,
                }
                cache_result = (
                    self.cache_manager.get_translation(
                        text,
                        "deeplx",
                        **cache_params,
                    )
                    if self.use_cache
                    else None
                )

                if cache_result:
                    result[idx] = cache_result
                    logger.info(f"使用缓存的DeepLX翻译结果：{idx}")
                    continue

                response = self.session.post(
                    self.endpoint,
                    json={
                        "text": text,
                        "source_lang": "auto",
                        "target_lang": target_lang,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                translated_text = response.json()["data"]

                # 保存到缓存
                if self.use_cache:
                    self.cache_manager.set_translation(
                        text,
                        translated_text,
                        "deeplx",
                        **cache_params,
                    )

                result[idx] = translated_text
            except Exception as e:
                logger.error(f"DeepLX翻译失败 {idx}: {str(e)}")
                result[idx] = "ERROR"
        return result


class TranslatorFactory:
    """翻译器工厂类"""

    @staticmethod
    def create_translator(
        translator_type: TranslatorType,
        thread_num: int = 5,
        batch_num: int = 10,
        target_language: str = "Chinese",
        model: str = "gpt-4o-mini",
        custom_prompt: str = "",
        temperature: float = 0.7,
        is_reflect: bool = False,
        update_callback: Optional[Callable] = None,
        usage_callback: Optional[Callable] = None,
        timeout: int = 300,
        translation_max_length: int = 0,
        use_cache: bool = True,
        batch_context_enabled: bool = True,
        batch_context_max_chars: int = 300,
    ) -> BaseTranslator:
        """创建翻译器实例"""
        try:
            if translator_type == TranslatorType.OPENAI:
                return OpenAITranslator(
                    thread_num=thread_num,
                    batch_num=batch_num,
                    target_language=target_language,
                    model=model,
                    custom_prompt=custom_prompt,
                    is_reflect=is_reflect,
                    temperature=temperature,
                    update_callback=update_callback,
                    usage_callback=usage_callback,
                    timeout=timeout,
                    translation_max_length=translation_max_length,
                    use_cache=use_cache,
                    batch_context_enabled=batch_context_enabled,
                    batch_context_max_chars=batch_context_max_chars,
                )
            elif translator_type == TranslatorType.GOOGLE:
                batch_num = 5
                return GoogleTranslator(
                    thread_num=thread_num,
                    batch_num=batch_num,
                    target_language=target_language,
                    update_callback=update_callback,
                    usage_callback=usage_callback,
                    use_cache=use_cache,
                    batch_context_enabled=batch_context_enabled,
                    batch_context_max_chars=batch_context_max_chars,
                )
            elif translator_type == TranslatorType.BING:
                batch_num = 10
                return BingTranslator(
                    thread_num=thread_num,
                    batch_num=batch_num,
                    target_language=target_language,
                    update_callback=update_callback,
                    usage_callback=usage_callback,
                    use_cache=use_cache,
                    batch_context_enabled=batch_context_enabled,
                    batch_context_max_chars=batch_context_max_chars,
                )
            elif translator_type == TranslatorType.DEEPLX:
                batch_num = 5
                return DeepLXTranslator(
                    thread_num=thread_num,
                    batch_num=batch_num,
                    target_language=target_language,
                    update_callback=update_callback,
                    usage_callback=usage_callback,
                    use_cache=use_cache,
                    batch_context_enabled=batch_context_enabled,
                    batch_context_max_chars=batch_context_max_chars,
                )
            else:
                raise ValueError(f"不支持的翻译器类型：{translator_type}")
        except Exception as e:
            logger.error(f"创建翻译器失败：{str(e)}")
            raise
