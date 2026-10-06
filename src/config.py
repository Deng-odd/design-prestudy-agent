"""V1 系统配置；读取项目 .env，已有环境变量优先，不接入 Provider。"""

import math
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def _integer(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} 必须为整数") from None
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} 超出 V1 允许范围")
    return value


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} 必须为 true 或 false")
    return value == "true"


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "qwen")
LLM_MODEL = os.getenv("LLM_MODEL", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")


def _number(name: str, default: float, minimum: float, maximum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} 必须为数字") from None
    if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} 超出允许范围")
    return value


LLM_TIMEOUT_SECONDS = _number("LLM_TIMEOUT_SECONDS", 60, 0.001)
LLM_MAX_TOKENS = _integer("LLM_MAX_TOKENS", 4096, 1)
LLM_TEMPERATURE_DECISION = _number("LLM_TEMPERATURE_DECISION", 0.0, 0, 2)
LLM_TEMPERATURE_ANALYSIS = _number("LLM_TEMPERATURE_ANALYSIS", 0.3, 0, 2)
LLM_TEMPERATURE_GENERATION = _number("LLM_TEMPERATURE_GENERATION", 0.7, 0, 2)


def validate_llm_config() -> None:
    """允许无凭据导入和离线测试，仅在实际调用前要求完整运行配置。"""
    if LLM_PROVIDER != "qwen":
        raise ValueError("当前 LLM Provider 不受支持")
    if not LLM_MODEL.strip():
        raise ValueError("请配置 LLM_MODEL")
    if not DASHSCOPE_API_KEY.strip():
        raise ValueError("请配置 DASHSCOPE_API_KEY")
    try:
        endpoint = urlsplit(LLM_BASE_URL)
        valid = endpoint.scheme == "https" and bool(endpoint.hostname) and not endpoint.username and not endpoint.password
        endpoint.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("LLM_BASE_URL 必须为有效 HTTPS endpoint")

WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", "tavily")
WEB_SEARCH_MAX_RESULTS = _integer("WEB_SEARCH_MAX_RESULTS", 10, 1)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# 图像凭据与 endpoint 复用 LLM 配置，技术重试独立。
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "qwen")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "qwen-image-3.0-pro")
IMAGE_TIMEOUT_SECONDS = _number("IMAGE_TIMEOUT_SECONDS", 120, 0.001)
IMAGE_MAX_RETRIES = _integer("IMAGE_MAX_RETRIES", 2, 0)


def image_reference_limit() -> int:
    """仅暴露已确认的参考图能力，不让 Skill 依赖 Provider 参数。"""
    if IMAGE_PROVIDER == "qwen" and IMAGE_MODEL in {"qwen-image-3.0-pro", "qwen-image-3.0"}:
        return 3
    return 0


def validate_image_config() -> None:
    if IMAGE_PROVIDER != "qwen":
        raise ValueError("当前 Image Provider 不受支持")
    if not IMAGE_MODEL.strip():
        raise ValueError("请配置 IMAGE_MODEL")
    if not DASHSCOPE_API_KEY.strip():
        raise ValueError("请配置 DASHSCOPE_API_KEY")
    try:
        endpoint = urlsplit(LLM_BASE_URL)
        valid = endpoint.scheme == "https" and bool(endpoint.hostname) and not endpoint.username and not endpoint.password
        endpoint.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("LLM_BASE_URL 必须为有效 HTTPS endpoint")

MAX_SEARCH_ATTEMPTS = _integer("MAX_SEARCH_ATTEMPTS", 2, 1, 2)
MAX_CONCEPT_REGENERATIONS = _integer("MAX_CONCEPT_REGENERATIONS", 1, 0, 1)
USE_IMG2IMG = _boolean("USE_IMG2IMG", False)
TOOL_MAX_RETRIES = _integer("TOOL_MAX_RETRIES", 2, 0)
LLM_MAX_RETRIES = _integer("LLM_MAX_RETRIES", 2, 0)
