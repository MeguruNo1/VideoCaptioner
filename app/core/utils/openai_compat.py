import os
from typing import Any, Dict, Optional


DEFAULT_LLM_TIMEOUT = 300
OPENAI_COMPAT_SERVICE_ENV = "OPENAI_COMPAT_SERVICE"
OPENAI_QWEN_ENABLE_THINKING_ENV = "OPENAI_QWEN_ENABLE_THINKING"


def is_qwen_service(service_name: Optional[str]) -> bool:
    return (service_name or "").strip().lower() == "qwen"


def is_deepseek_reasoner(
    service_name: Optional[str], model_name: Optional[str] = None
) -> bool:
    service_ok = (service_name or "").strip().lower() == "deepseek"
    model_text = (model_name or "").strip().lower()
    return service_ok and "reasoner" in model_text


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_openai_compat_request_options(
    service_name: Optional[str] = None,
    model_name: Optional[str] = None,
    qwen_enable_thinking: Optional[bool] = None,
    default_timeout: int = DEFAULT_LLM_TIMEOUT,
) -> Dict[str, Any]:
    service_name = service_name or os.getenv(OPENAI_COMPAT_SERVICE_ENV, "")
    if qwen_enable_thinking is None:
        qwen_enable_thinking = parse_bool(
            os.getenv(OPENAI_QWEN_ENABLE_THINKING_ENV), False
        )

    options: Dict[str, Any] = {"timeout": default_timeout}
    if is_qwen_service(service_name):
        options["extra_body"] = {"enable_thinking": bool(qwen_enable_thinking)}
    return options


def format_openai_compat_error(
    error: Exception,
    service_name: Optional[str] = None,
    model_name: Optional[str] = None,
    qwen_enable_thinking: Optional[bool] = None,
) -> str:
    message = str(error)
    service_name = service_name or os.getenv(OPENAI_COMPAT_SERVICE_ENV, "")
    if "timed out" in message.lower() and is_qwen_service(service_name):
        return f"Qwen 请求超时: {message}"
    if "timed out" in message.lower() and is_deepseek_reasoner(service_name, model_name):
        return f"DeepSeek 请求超时: {message}"
    return message


def extract_openai_usage(response: Any) -> Dict[str, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _read(name: str) -> int:
        value = getattr(usage, name, 0)
        return int(value or 0)

    return {
        "prompt_tokens": _read("prompt_tokens"),
        "completion_tokens": _read("completion_tokens"),
        "total_tokens": _read("total_tokens"),
    }
