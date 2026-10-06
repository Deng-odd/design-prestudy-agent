import base64
from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock, Mock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError
from openai.types import ImagesResponse

from src import config
from src.tools import generate_image
from src.tools.image_generation import ImageGenerationError

tool = import_module("src.tools.image_generation")


def response(url="https://example.com/generated.png"):
    return ImagesResponse.model_validate({"created": 0, "data": [{"url": url}]})


@pytest.fixture
def sdk(monkeypatch):
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "test-only-placeholder")
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://example.invalid/compatible-mode/v1")
    client = MagicMock()
    client.__enter__.return_value = client
    client.images.generate.return_value = response()
    constructor = Mock(return_value=client)
    monkeypatch.setattr(tool, "OpenAI", constructor)
    monkeypatch.setattr(tool, "sleep", Mock())
    return constructor, client.images.generate


def test_text2img_config_request_and_normalization(sdk):
    result = generate_image("空间意向", size="1024x1024")
    sdk[0].assert_called_once_with(api_key=config.DASHSCOPE_API_KEY, base_url=config.LLM_BASE_URL,
                                   timeout=120, max_retries=0)
    sdk[1].assert_called_once_with(model=config.IMAGE_MODEL, prompt="空间意向", n=1,
                                   response_format="url", size="1024x1024")
    assert result == {"image_url": "https://example.com/generated.png", "provider": "qwen",
                      "model": config.IMAGE_MODEL, "mode": "text2img"}
    assert "State" not in generate_image.__annotations__


@pytest.mark.parametrize("extension,data,mime", [(".png", b"\x89PNG\r\n\x1a\n", "image/png"),
                                                 (".jpg", b"\xff\xd8\xff", "image/jpeg"),
                                                 (".JPEG", b"\xff\xd8\xff", "image/jpeg")])
def test_reference_request_and_base64(sdk, tmp_path, extension, data, mime):
    path = tmp_path / ("site" + extension)
    path.write_bytes(data)
    references = [str(path)]
    assert generate_image("参考场地", reference_images=references)["mode"] == "img2img"
    params = sdk[1].call_args.kwargs
    uri = params["extra_body"]["image"][0]
    assert uri.startswith(f"data:{mime};base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == data
    assert "reference_strength" not in params and references == [str(path)]


@pytest.mark.parametrize("failure", ["missing", "unreadable", "format", "content", "large"])
def test_invalid_references_never_call_sdk(sdk, tmp_path, monkeypatch, failure):
    path = tmp_path / ("site.gif" if failure == "format" else "site.png")
    if failure != "missing":
        path.write_bytes(b"invalid" if failure == "content" else b"\x89PNG\r\n\x1a\n")
    if failure == "unreadable":
        monkeypatch.setattr(Path, "read_bytes", Mock(side_effect=PermissionError()))
    if failure == "large":
        monkeypatch.setattr(Path, "stat", Mock(return_value=Mock(st_size=11 * 1024 * 1024)))
    with pytest.raises(ImageGenerationError):
        generate_image("场地", reference_images=[str(path)])
    sdk[0].assert_not_called()


def error(kind):
    request = httpx.Request("POST", "https://example.invalid/images/generations")
    if kind == "timeout":
        return APITimeoutError(request=request)
    if kind == "network":
        return APIConnectionError(request=request)
    return APIStatusError("private response", response=httpx.Response(kind, request=request), body={})


@pytest.mark.parametrize("kind", ["timeout", "network", 408, 429, 503])
def test_transient_retry_is_separate(sdk, monkeypatch, kind):
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 0)
    monkeypatch.setattr(config, "TOOL_MAX_RETRIES", 0)
    monkeypatch.setattr(config, "IMAGE_MAX_RETRIES", 1)
    sdk[1].side_effect = [error(kind), response()]
    assert generate_image("概念")["image_url"]
    assert sdk[1].call_count == 2 and tool.sleep.call_count == 1


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_retry_limit(sdk, monkeypatch, retries):
    monkeypatch.setattr(config, "IMAGE_MAX_RETRIES", retries)
    sdk[1].side_effect = error("timeout")
    with pytest.raises(ImageGenerationError):
        generate_image("概念")
    assert sdk[1].call_count == retries + 1 and tool.sleep.call_count == retries


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_permanent_failure_never_retries_or_leaks(sdk, status):
    sdk[1].side_effect = error(status)
    with pytest.raises(ImageGenerationError) as caught:
        generate_image("概念")
    assert str(status) in str(caught.value) and "private" not in str(caught.value)
    assert sdk[1].call_count == 1


@pytest.mark.parametrize("url", [None, "", "file:///image.png", "https://user:secret@example.com/image.png"])
def test_invalid_output_is_controlled(sdk, url):
    sdk[1].return_value = response(url)
    with pytest.raises(ImageGenerationError):
        generate_image("概念")
    assert sdk[1].call_count == 1


@pytest.mark.parametrize("size", ["1024*1024", "1x1", "10000x512", 123])
def test_bad_size_is_controlled(sdk, size):
    with pytest.raises(ImageGenerationError):
        generate_image("概念", size=size)
    sdk[0].assert_not_called()


@pytest.mark.parametrize("setting,value", [("DASHSCOPE_API_KEY", ""), ("IMAGE_MODEL", ""),
                                         ("IMAGE_PROVIDER", "unsupported"), ("LLM_BASE_URL", "http://example.com")])
def test_missing_or_invalid_config_never_calls_sdk(sdk, monkeypatch, setting, value):
    monkeypatch.setattr(config, setting, value)
    with pytest.raises(ImageGenerationError):
        generate_image("概念")
    sdk[0].assert_not_called()


def test_reference_capability_and_count(sdk, monkeypatch):
    with pytest.raises(ImageGenerationError):
        generate_image("概念", reference_images=["site.png"] * 4)
    monkeypatch.setattr(config, "IMAGE_MODEL", "unverified-model")
    with pytest.raises(ImageGenerationError):
        generate_image("概念", reference_images=["site.png"])
    # 未确认的模型仍允许调用其纯文本接口，不擅自替换模型。
    assert generate_image("概念")["mode"] == "text2img"
    assert sdk[1].call_count == 1
