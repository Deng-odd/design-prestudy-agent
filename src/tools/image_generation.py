"""Qwen Image 同步调用与标准化；不读取 State 或选择业务模式。"""

import base64
import re
from pathlib import Path
from time import sleep
from urllib.parse import urlsplit

from openai import APIConnectionError, APIStatusError, OpenAI

from src import config


class ImageGenerationError(RuntimeError):
    """受控图像调用错误，不暴露凭据、参考图数据或原始响应。"""


def _encode_image(filename: str) -> str:
    path = Path(filename)
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ImageGenerationError("参考图仅支持 PNG/JPG/JPEG")
    try:
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ImageGenerationError("参考图超过 10MB")
        data = path.read_bytes()
    except OSError:
        raise ImageGenerationError("参考图不存在或不可读") from None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    else:
        raise ImageGenerationError("参考图内容不是 PNG/JPEG")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _validate_size(size: str | None) -> None:
    if size is None or size == "auto":
        return
    if not isinstance(size, str) or not re.fullmatch(r"[1-9]\d{0,4}x[1-9]\d{0,4}", size):
        raise ImageGenerationError("图片 size 必须为 auto 或 宽x高")
    width, height = map(int, size.split("x"))
    if not 512 ** 2 <= width * height <= 2048 ** 2 or not 1 / 8 <= width / height <= 8:
        raise ImageGenerationError("图片 size 超出支持范围")


def generate_image(prompt: str, *, reference_images: list[str] | None = None,
                   size: str | None = None) -> dict:
    """生成一张图，返回 image_url/provider/model/mode；参考图由调用方选择。"""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ImageGenerationError("Image Prompt 必须为非空字符串")
    if reference_images is not None and (not isinstance(reference_images, list) or
                                        any(not isinstance(item, str) or not item for item in reference_images)):
        raise ImageGenerationError("reference_images 必须为图片路径列表")
    references = list(reference_images or [])
    try:
        config.validate_image_config()
    except ValueError as error:
        raise ImageGenerationError(str(error)) from None
    if references and (not config.image_reference_limit() or len(references) > config.image_reference_limit()):
        raise ImageGenerationError("当前图像模型不支持指定数量的参考图")
    _validate_size(size)
    params = {"model": config.IMAGE_MODEL, "prompt": prompt, "n": 1, "response_format": "url"}
    if size is not None:
        params["size"] = size
    if references:
        params["extra_body"] = {"image": [_encode_image(path) for path in references]}
    try:
        with OpenAI(api_key=config.DASHSCOPE_API_KEY, base_url=config.LLM_BASE_URL,
                    timeout=config.IMAGE_TIMEOUT_SECONDS, max_retries=0) as client:
            for attempt in range(config.IMAGE_MAX_RETRIES + 1):
                try:
                    response = client.images.generate(**params)
                    url = response.data[0].url if response.data else None
                    try:
                        parsed = urlsplit(url) if isinstance(url, str) else None
                        valid = parsed and parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password
                        if parsed:
                            parsed.port
                    except ValueError:
                        valid = False
                    if not valid:
                        raise ImageGenerationError("图像接口未返回有效图片 URL")
                    return {"image_url": url, "provider": config.IMAGE_PROVIDER,
                            "model": config.IMAGE_MODEL, "mode": "img2img" if references else "text2img"}
                except (APIConnectionError, APIStatusError) as error:
                    retryable = isinstance(error, APIConnectionError) or error.status_code in {408, 429} or error.status_code >= 500
                    if not retryable or attempt >= config.IMAGE_MAX_RETRIES:
                        detail = f"（HTTP {error.status_code}）" if isinstance(error, APIStatusError) else "（网络或超时）"
                        raise ImageGenerationError("图像调用最终失败" + detail) from None
                    sleep(min(2 ** attempt, 4))
    except ImageGenerationError:
        raise
    except Exception:
        raise ImageGenerationError("图像客户端或响应不可用") from None
