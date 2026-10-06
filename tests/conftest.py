"""共享测试输入；默认测试禁止真实网络且不使用本地密钥。"""

from urllib.parse import urlsplit
from unittest.mock import Mock
import json
import socket

import pytest
import requests
from tavily import TavilyClient

from src import config
from src.schemas import Case, CaseAnalysis, Concept, DesignOpportunity, SiteAnalysis, SWOT, Vision


def pytest_addoption(parser):
    parser.addoption("--qwen-multimodal", action="store_true", help="当前模型已确认支持图片时启用真实多模态 smoke test")
    parser.addoption("--agent-smoke", action="store_true", help="启用真实 Agent smoke test（需要两套 Provider 凭据）")


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch, request):
    if request.node.get_closest_marker("integration"):
        if request.config.option.markexpr != "integration":
            pytest.skip("默认测试保持离线；真实验证请显式使用 -m integration")
        yield
        return
    monkeypatch.setattr(config, "TAVILY_API_KEY", "")
    monkeypatch.setattr(config, "WEB_SEARCH_PROVIDER", "tavily")
    monkeypatch.setattr(config, "WEB_SEARCH_MAX_RESULTS", 10)
    monkeypatch.setattr(config, "TOOL_MAX_RETRIES", 2)
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 2)
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "")
    monkeypatch.setattr(config, "LLM_MODEL", "")
    monkeypatch.setattr(config, "IMAGE_PROVIDER", "qwen")
    monkeypatch.setattr(config, "IMAGE_MODEL", "qwen-image-3.0-pro")
    monkeypatch.setattr(config, "IMAGE_TIMEOUT_SECONDS", 120)
    monkeypatch.setattr(config, "IMAGE_MAX_RETRIES", 2)
    monkeypatch.setattr(config, "USE_IMG2IMG", False)
    attempted = []
    original_connect = socket.socket.connect

    def deny_network(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("默认测试不得访问外部网络")

    def connect_local_only(connection, address):
        # Windows asyncio 的 socketpair 使用本机回环，不是外部 Provider 访问。
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(connection, address)
        return deny_network()

    monkeypatch.setattr(requests.Session, "request", deny_network)
    monkeypatch.setattr(socket.socket, "connect", connect_local_only)
    yield
    assert not attempted, "测试曾尝试访问外部网络"


@pytest.fixture
def search_hit():
    case = Case(name="滨水公共空间项目", location="示例城市", project_type="公共空间",
                source="https://example.com/project", relevance="公共空间研究")
    return {
        "title": case.name, "url": case.source, "source": urlsplit(case.source).hostname,
        "snippet": f"项目地点：{case.location}。项目通过步行路径连接公共空间与滨水公园。",
    }


@pytest.fixture
def sdk_search(monkeypatch):
    """替换唯一外部调用，仍走实际 Tool 和 SDK 客户端生命周期。"""
    from importlib import import_module
    tool = import_module("src.tools.web_search")
    monkeypatch.setattr(config, "TAVILY_API_KEY", "test-only-placeholder")
    monkeypatch.setattr(tool, "sleep", Mock())
    search = Mock(return_value={"results": []})
    monkeypatch.setattr(TavilyClient, "search", search)
    return search


def make_site():
    return SiteAnalysis(project_positioning="滨水公共空间", location_conditions={"description": "示例城市"},
                        functional_conditions={}, landscape_resources={}, public_space={}, transportation={},
                        spatial_conditions={"description": "北侧临道路"},
                        swot=SWOT(strengths=["滨水资源"], weaknesses=[], opportunities=[], threats=[]),
                        analysis_summary="需联系滨水资源与公共活动")


class FakeLLM:
    """仅替代公共 LLM 接口，所有业务函数、校验和路由照常执行。"""
    def __init__(self):
        self.calls = []
        self.sufficient = True
        self.need_cases = False
        self.research_checks = []
        self.quality = ["PASS"]
        self.generation_count = 0

    def _input(self, prompt, kwargs):
        task = prompt.split("当前任务：", 1)[1].split("\n", 1)[0]
        inputs = json.loads(prompt.split("INPUT_JSON:\n", 1)[1])
        self.calls.append((task, inputs, kwargs))
        return task, inputs

    def structured(self, prompt, schema, **kwargs):
        task, inputs = self._input(prompt, kwargs)
        if task == "parse_and_check":
            return schema(project_background=inputs["user_input"], location="示例城市", planning_conditions={},
                          client_requirements="研究公共空间案例" if self.need_cases else None,
                          site_image_description="图片显示场地空间" if kwargs.get("images") else "",
                          info_sufficient=self.sufficient,
                          missing_critical=[] if self.sufficient else ["项目定位与空间信息"],
                          missing_optional=["具体规划指标"], followup_question="" if self.sufficient else "请补充项目定位与空间信息。")
        if task == "site_analysis":
            return schema.model_validate(make_site().model_dump())
        if task == "check_case_need":
            return schema(need_case_research=self.need_cases, research_direction=["公共空间"] if self.need_cases else [])
        if task in {"generate_search_queries", "refine_search"}:
            return schema(search_queries=["公共空间 设计案例" if task == "generate_search_queries" else "公共空间 慢行联系 设计案例"])
        if task == "analyze_cases":
            cases, analyses = [], []
            for result in inputs["search_results"]:
                case = Case(name=result["title"], location="摘要未明确位置", project_type="公共空间",
                            source=result["url"], relevance=f"专业推理：公共空间参考；来源域名：{result['source']}")
                cases.append(case)
                analyses.append(CaseAnalysis(case=case.name, relevance_reason="与当前公共空间研究有关",
                                             spatial_strategy=["来源摘要：" + result["snippet"]],
                                             applicable_reference=["专业推理：比较公共节点连接"],
                                             limitations=["仅有摘要，未核验全文；" + case.source]))
            return schema(filtered_cases=cases, case_analysis=analyses)
        if task == "check_research":
            enough = self.research_checks.pop(0) if self.research_checks else bool(inputs["filtered_cases"])
            return schema(research_sufficient=enough, research_gaps=[] if enough else ["缺少可追溯空间策略"])
        if task == "opportunities_and_vision":
            return schema(opportunities=[DesignOpportunity(opportunity="串联公共节点", basis="滨水与道路联系", priority="high")],
                          vision=Vision(theme="滨水共享", positioning="公共空间", core_goal="提升空间联系", spatial_idea="连续开放节点"))
        if task in {"generate_concepts", "regenerate_concepts"}:
            self.generation_count += 1
            return schema(concepts=[Concept(name=name, core_concept=name, design_opportunities=["串联公共节点"],
                                             spatial_strategy=strategy, key_actions=[strategy], case_references=[])
                                    for name, strategy in [("滨水联系", "连接滨水慢行路径"), ("活动节点", "组织公共活动节点")]])
        raise AssertionError("未知任务 " + task)

    def text(self, prompt, **kwargs):
        task, inputs = self._input(prompt, kwargs)
        if task == "quality_check":
            return self.quality.pop(0)
        if task == "image_reference_check":
            return "PASS"
        if task == "image_prompt":
            return inputs["vision"]["theme"] + "；" + inputs["concept"]["name"] + "；" + inputs["concept"]["spatial_strategy"]
        if task == "compose_report":
            return "# 前期研究报告\n\n" + inputs["site_analysis"]["analysis_summary"] + "\n\n" + "\n".join(
                item["name"] + "：" + item["spatial_strategy"] for item in inputs["concepts"]
            ) + "\n" + "\n".join(item["source"] for item in inputs["project_context"]["filtered_cases"]) + "\n" + "\n".join(
                f"![{image['concept_name']}]({image['image_url']})" for image in inputs["images"])
        raise AssertionError("未知文本任务 " + task)


@pytest.fixture
def fake_llm(monkeypatch):
    from src.agent import nodes
    from src.skills import site_analysis, case_research, concept_generation, report_composition
    fake = FakeLLM()
    for module in (nodes, site_analysis, case_research, concept_generation):
        monkeypatch.setattr(module, "call_llm_structured", fake.structured)
    monkeypatch.setattr(concept_generation, "call_llm", fake.text)
    monkeypatch.setattr(report_composition, "call_llm", fake.text)
    from src.tools.image_generation import ImageGenerationError
    monkeypatch.setattr(concept_generation, "generate_image", Mock(side_effect=ImageGenerationError("离线图片失败降级")))
    return fake


@pytest.fixture
def fake_image(fake_llm, monkeypatch):
    """标准 Tool 输出由既有图片 Schema 创建，不绕过业务契约。"""
    from src.schemas import GeneratedImage
    from src.skills import concept_generation
    def generate(prompt, *, reference_images=None, size=None):
        image = GeneratedImage(concept_name="Tool 不处理概念", image_url="https://example.com/concept.png",
                               prompt=prompt, mode="img2img" if reference_images else "text2img",
                               reference_images=reference_images or [])
        return {"image_url": image.image_url, "mode": image.mode, "provider": "test", "model": "test"}
    tool = Mock(side_effect=generate)
    monkeypatch.setattr(concept_generation, "generate_image", tool)
    return tool
