"""真实 Provider smoke tests：仅显式 -m integration 时允许联网。"""

import struct
import zlib
from urllib.parse import urlsplit

import pytest
from pydantic import BaseModel, ConfigDict, Field

from src import config
from src.agent.graph import graph
from src.agent.state import create_initial_state
from src.llm import call_llm, call_llm_structured
from src.tools import generate_image, web_search

pytestmark = pytest.mark.integration


class SmokeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: str = Field(min_length=1)


def require_qwen():
    if not config.DASHSCOPE_API_KEY.strip() or not config.LLM_MODEL.strip():
        pytest.skip("缺少 DASHSCOPE_API_KEY 或 LLM_MODEL")


def require_search():
    if not config.TAVILY_API_KEY.strip():
        pytest.skip("缺少 TAVILY_API_KEY")


def test_qwen_text():
    require_qwen()
    result = call_llm("请简短回复：连接成功。", temperature=config.LLM_TEMPERATURE_DECISION, max_tokens=128)
    assert isinstance(result, str) and result.strip()


def test_qwen_structured():
    require_qwen()
    result = call_llm_structured("返回一个 JSON 对象，message 为简短的连接成功说明。", SmokeResult,
                                  temperature=config.LLM_TEMPERATURE_DECISION, max_tokens=256)
    assert isinstance(result, SmokeResult) and result.message.strip()


def test_qwen_multimodal(request, tmp_path):
    require_qwen()
    if not request.config.getoption("--qwen-multimodal"):
        pytest.skip("未确认当前模型的图片能力；确认后使用 --qwen-multimodal，不切换模型")
    # 本地合成小色块作为输入 fixture，不调用任何图像生成或下载服务。
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", 32, 32, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff\x00\x00" * 32) * 32)) + chunk(b"IEND", b"")
    path = tmp_path / "smoke_input.png"
    path.write_bytes(png)
    result = call_llm("用一句话描述图片的主要颜色。", images=[str(path)],
                       temperature=config.LLM_TEMPERATURE_DECISION, max_tokens=128)
    assert isinstance(result, str) and result.strip()


def test_tavily_normalized_result():
    require_search()
    results = web_search("urban public space waterfront project", max_results=3)
    assert isinstance(results, list) and results
    for item in results:
        assert set(item) == {"title", "url", "snippet", "source"}
        assert all(isinstance(value, str) for value in item.values())
        assert urlsplit(item["url"]).hostname == item["source"]


def test_agent_smoke(request):
    require_qwen()
    require_search()
    if not request.config.getoption("--agent-smoke"):
        pytest.skip("可选完整 Agent smoke test，使用 --agent-smoke 启用")
    state = graph.invoke(create_initial_state(
        "项目为城市滨水公共空间更新。北侧临城市道路，南侧临河，现有步行空间与活动节点缺乏联系。"
        "以提升公共活动和慢行联系为设计目标。请研究有可追溯来源的滨水公共空间案例，再形成概念研究报告。"
    ), config={"recursion_limit": 20})
    assert isinstance(state.get("final_report"), str) and state["final_report"].strip()
    assert 0 <= state["search_attempts"] <= 2


def require_image():
    if not config.DASHSCOPE_API_KEY.strip() or not config.IMAGE_MODEL.strip():
        pytest.skip("缺少 DASHSCOPE_API_KEY 或 IMAGE_MODEL")


def test_qwen_image_text2img():
    require_image()
    result = generate_image("城市公园概念意向：绿地、步行小径和公共活动节点，简洁鸟瞰构图。", size="512x512")
    assert result["mode"] == "text2img"
    assert urlsplit(result["image_url"]).scheme == "https"
    assert set(result) == {"image_url", "provider", "model", "mode"}


def test_qwen_image_reference(tmp_path):
    require_image()
    if not config.image_reference_limit():
        pytest.skip("当前配置的图像模型未确认支持参考图")
    # 本地合成 512px 场地示意作为输入；不下载图像，不测试美学。
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    row = b"\x80\xa0\x60" * 320 + b"\x50\x90\xc0" * 192
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", 512, 512, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress((b"\x00" + row) * 512)) + chunk(b"IEND", b"")
    path = tmp_path / "image_reference.png"
    path.write_bytes(png)
    result = generate_image("保留参考图的绿地与滨水色块关系，表达有步行路径的城市公园概念鸟瞰意向。",
                            reference_images=[str(path)], size="512x512")
    assert result["mode"] == "img2img"
    assert urlsplit(result["image_url"]).scheme == "https"
    assert set(result) == {"image_url", "provider", "model", "mode"}
