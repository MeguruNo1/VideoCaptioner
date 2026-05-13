import hashlib
import json
import re
from pathlib import Path
from string import Template
from typing import Any

from app.core.utils import json_repair
from app.core.utils.openai_compat import get_openai_compat_request_options


GENERATED_TERMS_BEGIN = "<!-- AI_VIDEO_TRANSCRIPT_TERMS_BEGIN -->"
GENERATED_TERMS_END = "<!-- AI_VIDEO_TRANSCRIPT_TERMS_END -->"


def _clean_term_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\r\n`'\"“”‘’")


def parse_glossary_text(glossary_text: str) -> dict[str, str]:
    glossary = {}
    for raw_line in str(glossary_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for separator in ("->", "=>", "=", "：", ":"):
            if separator in line:
                original, translation = line.split(separator, 1)
                original = _clean_term_text(original)
                translation = _clean_term_text(translation)
                if original and translation:
                    glossary[original.casefold()] = translation
                break
    return glossary


def parse_ai_terms_response(response_text: str, glossary_text: str = "") -> list[dict[str, str]]:
    data = json_repair.loads(response_text)
    raw_terms = data.get("terms", data) if isinstance(data, dict) else data
    glossary = parse_glossary_text(glossary_text)
    terms = []
    seen = set()

    for item in raw_terms or []:
        if isinstance(item, str):
            original = _clean_term_text(item)
            translation = ""
            category = "term"
        elif isinstance(item, dict):
            original = _clean_term_text(
                item.get("original")
                or item.get("source")
                or item.get("name")
                or item.get("term")
            )
            translation = _clean_term_text(
                item.get("translation") or item.get("target") or item.get("zh")
            )
            category = _clean_term_text(item.get("category") or item.get("type") or "term")
        else:
            continue

        if not original:
            continue
        translation = glossary.get(original.casefold(), translation)
        key = original.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(
            {
                "original": original,
                "translation": translation,
                "category": category or "term",
            }
        )

    return terms


def merge_hotwords(existing_hotwords: str, terms: list[dict[str, str]]) -> str:
    values = []
    seen = set()
    for value in re.split(r"[,，;\n\r]+", str(existing_hotwords or "")):
        text = _clean_term_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            values.append(text)
    for term in terms:
        text = _clean_term_text(term.get("original"))
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            values.append(text)
    return ", ".join(values)


def format_terms_for_document_prompt(terms: list[dict[str, str]]) -> str:
    rows = []
    for term in terms:
        original = _clean_term_text(term.get("original"))
        translation = _clean_term_text(term.get("translation"))
        if not original:
            continue
        if translation:
            rows.append(f"- {original} -> {translation}")
        else:
            rows.append(f"- {original}")
    if not rows:
        return ""
    return "\n".join(
        [
            GENERATED_TERMS_BEGIN,
            "AI 根据视频文稿提取的名称和术语，翻译与校正时优先遵循：",
            *rows,
            GENERATED_TERMS_END,
        ]
    )


def merge_document_prompt(existing_prompt: str, terms: list[dict[str, str]]) -> str:
    generated = format_terms_for_document_prompt(terms)
    existing = str(existing_prompt or "").strip()
    pattern = re.compile(
        rf"\n*{re.escape(GENERATED_TERMS_BEGIN)}.*?{re.escape(GENERATED_TERMS_END)}\n*",
        re.S,
    )
    existing = pattern.sub("\n", existing).strip()
    if not generated:
        return existing
    if existing:
        return f"{existing}\n\n{generated}"
    return generated


def format_terms_txt(terms: list[dict[str, str]]) -> str:
    lines = ["原文\t译文\t类型"]
    for term in terms:
        lines.append(
            "\t".join(
                [
                    _clean_term_text(term.get("original")),
                    _clean_term_text(term.get("translation")),
                    _clean_term_text(term.get("category")),
                ]
            )
        )
    return "\n".join(lines)


def _resolve_current_llm_settings() -> dict[str, Any]:
    from app.common.config import cfg
    from app.core.entities import LLMServiceEnum

    current_service = cfg.llm_service.value
    if current_service == LLMServiceEnum.OPENAI:
        base_url = cfg.openai_api_base.value
        api_key = cfg.openai_api_key.value
        model = cfg.openai_model.value
    elif current_service == LLMServiceEnum.SILICON_CLOUD:
        base_url = cfg.silicon_cloud_api_base.value
        api_key = cfg.silicon_cloud_api_key.value
        model = cfg.silicon_cloud_model.value
    elif current_service == LLMServiceEnum.DEEPSEEK:
        base_url = cfg.deepseek_api_base.value
        api_key = cfg.deepseek_api_key.value
        model = cfg.deepseek_model.value
    elif current_service == LLMServiceEnum.OLLAMA:
        base_url = cfg.ollama_api_base.value
        api_key = cfg.ollama_api_key.value
        model = cfg.ollama_model.value
    elif current_service == LLMServiceEnum.LM_STUDIO:
        base_url = cfg.lm_studio_api_base.value
        api_key = cfg.lm_studio_api_key.value
        model = cfg.lm_studio_model.value
    elif current_service == LLMServiceEnum.GEMINI:
        base_url = cfg.gemini_api_base.value
        api_key = cfg.gemini_api_key.value
        model = cfg.gemini_model.value
    elif current_service == LLMServiceEnum.CHATGLM:
        base_url = cfg.chatglm_api_base.value
        api_key = cfg.chatglm_api_key.value
        model = cfg.chatglm_model.value
    elif current_service == LLMServiceEnum.QWEN:
        base_url = cfg.qwen_api_base.value
        api_key = cfg.qwen_api_key.value
        model = cfg.qwen_model.value
    elif current_service == LLMServiceEnum.PUBLIC:
        base_url = cfg.public_api_base.value
        api_key = cfg.public_api_key.value
        model = cfg.public_model.value
    else:
        base_url = ""
        api_key = ""
        model = ""

    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "service": current_service.value,
        "timeout": cfg.llm_request_timeout.value,
        "qwen_enable_thinking": cfg.qwen_enable_thinking.value,
    }


def _build_term_extraction_messages(
    transcript_text: str, glossary_text: str, target_language: str
) -> list[dict[str, str]]:
    system_prompt = """
你是视频字幕术语整理助手。请从视频文稿中提取人名、角色名、组织名、产品名、作品名、地点名、专业术语和高频专有名词。

规则：
- 优先使用用户词库中的译名；词库没有时，根据上下文给出适合${target_language}字幕翻译的译名。
- 如果 AI 判断与用户词库存在冲突、争议或不确定，必须以用户词库为准，不要自行改写词库译名。
- 只保留对转录纠错或字幕翻译有帮助的名称/术语。
- 不要提取普通虚词、泛泛名词或完整句子。
- 原文必须保留文稿中的写法或最可能的标准写法。
- 最多返回 80 条。
- 只返回纯 JSON，不要 Markdown，不要解释文字。

输出格式：
{
  "terms": [
    {"original": "Original Name", "translation": "译名", "category": "person|organization|place|product|work|term"}
  ]
}
"""
    user_content = "\n".join(
        [
            "用户词库：",
            glossary_text.strip() or "（空）",
            "",
            "视频文稿：",
            transcript_text,
        ]
    )
    return [
        {
            "role": "system",
            "content": Template(system_prompt).safe_substitute(
                target_language=target_language or "目标语言"
            ),
        },
        {"role": "user", "content": user_content},
    ]


def extract_terms_with_ai(
    transcript_text: str,
    glossary_text: str,
    target_language: str,
) -> list[dict[str, str]]:
    settings = _resolve_current_llm_settings()
    if not settings["base_url"] or not settings["api_key"] or not settings["model"]:
        raise ValueError("LLM API 未配置，无法提取视频文稿术语")

    from openai import OpenAI

    messages = _build_term_extraction_messages(
        transcript_text[:24000],
        glossary_text,
        target_language,
    )
    client = OpenAI(base_url=settings["base_url"], api_key=settings["api_key"])
    response = client.chat.completions.create(
        model=settings["model"],
        messages=messages,
        temperature=0.1,
        **get_openai_compat_request_options(
            service_name=settings["service"],
            model_name=settings["model"],
            qwen_enable_thinking=settings["qwen_enable_thinking"],
            default_timeout=settings["timeout"],
        ),
    )
    return parse_ai_terms_response(response.choices[0].message.content, glossary_text)


def apply_terms_to_prompt_settings(terms: list[dict[str, str]]) -> dict[str, str]:
    from app.common.config import cfg

    hotwords = merge_hotwords(cfg.whisperx_hotwords.value, terms)
    document_prompt = merge_document_prompt(cfg.custom_prompt_text.value, terms)
    cfg.set(cfg.whisperx_hotwords, hotwords)
    cfg.set(cfg.custom_prompt_text, document_prompt)
    return {"whisperx_hotwords": hotwords, "custom_prompt_text": document_prompt}


def write_terms_txt_file(terms: list[dict[str, str]], work_dir: Path, filename_stem: str) -> str:
    digest = hashlib.md5(format_terms_txt(terms).encode("utf-8")).hexdigest()[:8]
    terms_path = work_dir / f"【AI术语表】{filename_stem}-{digest}.txt"
    work_dir.mkdir(parents=True, exist_ok=True)
    terms_path.write_text(format_terms_txt(terms), encoding="utf-8")
    return str(terms_path)
