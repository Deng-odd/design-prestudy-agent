import base64
import json
from unittest.mock import MagicMock, Mock

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, BadRequestError, AuthenticationError, InternalServerError, RateLimitError
from openai.types.chat import ChatCompletion

from src import config, llm
from src.schemas import Vision


def completion(text, finish="stop"):
    return ChatCompletion.model_validate({"id": "offline-response", "object": "chat.completion", "created": 0,
                                         "model": "configured-model", "choices": [{"index": 0, "finish_reason": finish,
                                             "message": {"role": "assistant", "content": text}}]})


def valid_vision():
    return Vision(theme="滨水共享", positioning="公共空间", core_goal="提升空间联系", spatial_idea="连续节点")


@pytest.fixture
def sdk(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "qwen")
    monkeypatch.setattr(config, "LLM_MODEL", "configured-model")
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "test-only-placeholder")
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://example.invalid/compatible-mode/v1")
    monkeypatch.setattr(config, "LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(config, "LLM_MAX_TOKENS", 4096)
    monkeypatch.setattr(config, "LLM_TEMPERATURE_ANALYSIS", 0.3)
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = completion("# Markdown report")
    constructor = Mock(return_value=client)
    monkeypatch.setattr(llm, "OpenAI", constructor)
    monkeypatch.setattr(llm, "sleep", Mock())
    return constructor, client.chat.completions.create


def test_text_config_defaults_and_response_boundary(sdk):
    constructor, create = sdk
    result = llm.call_llm("任务")
    assert result == "# Markdown report" and isinstance(result, str)
    constructor.assert_called_once_with(api_key=config.DASHSCOPE_API_KEY, base_url=config.LLM_BASE_URL,
                                       timeout=60, max_retries=0)
    params = create.call_args.kwargs
    assert params["model"] == config.LLM_MODEL
    assert params["max_tokens"] == 4096 and params["temperature"] == .3
    assert params["messages"][1] == {"role": "user", "content": "任务"}
    assert params["extra_body"] == {"enable_thinking": False}


@pytest.mark.parametrize("temperature", [0.0, 0.3, 0.7])
def test_temperature_and_explicit_max_tokens_are_forwarded(sdk, temperature):
    llm.call_llm("任务", temperature=temperature, max_tokens=1234)
    assert sdk[1].call_args.kwargs["temperature"] == temperature
    assert sdk[1].call_args.kwargs["max_tokens"] == 1234


def test_config_overrides_are_not_hardcoded(sdk, monkeypatch):
    monkeypatch.setattr(config, "LLM_TIMEOUT_SECONDS", 17)
    monkeypatch.setattr(config, "LLM_MAX_TOKENS", 512)
    monkeypatch.setattr(config, "LLM_MODEL", "another-configured-model")
    llm.call_llm("任务")
    assert sdk[0].call_args.kwargs["timeout"] == 17
    assert sdk[1].call_args.kwargs["max_tokens"] == 512
    assert sdk[1].call_args.kwargs["model"] == config.LLM_MODEL


def test_llm_retries_are_independent_of_tool_budget(sdk, monkeypatch):
    monkeypatch.setattr(config, "TOOL_MAX_RETRIES", 0)
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 1)
    sdk[1].side_effect = [provider_error("timeout"), completion("成功")]
    assert llm.call_llm("任务") == "成功"
    assert sdk[1].call_count == 2


def test_parse_no_image_empty_string_through_real_structured_flow(sdk):
    from src.agent import nodes
    from src.agent.state import create_initial_state
    parsed = nodes._ParsedInput(project_background="滨水研究", location="城市外围", planning_conditions={},
        client_requirements=None, site_image_description="", info_sufficient=True,
        missing_critical=[], missing_optional=[], followup_question="")
    sdk[1].return_value = completion(json.dumps(parsed.model_dump(), ensure_ascii=False))
    result = nodes.parse_and_check(create_initial_state("河流与湿地交界的公共空间研究"))
    assert result["site_image_description"] == ""
    nodes._ParsedInput.model_validate(result)
    prompt = sdk[1].call_args.kwargs["messages"][1]["content"]
    assert 'site_image_description 必须返回空字符串 ""' in prompt
    assert "禁止返回 null，禁止省略该字段" in prompt
    sdk[1].assert_called_once()


def test_parse_null_image_description_is_still_rejected(sdk, monkeypatch):
    from src.agent import nodes
    from src.agent.state import create_initial_state
    from pydantic import ValidationError
    data = nodes._ParsedInput(project_background="滨水研究", location="城市外围", planning_conditions={},
        client_requirements=None, site_image_description="", info_sufficient=True,
        missing_critical=[], missing_optional=[], followup_question="").model_dump()
    data["site_image_description"] = None  # Intentional invalid response: retain strict contract.
    with pytest.raises(ValidationError) as caught:
        nodes._ParsedInput.model_validate(data)
    assert caught.value.errors()[0]["loc"] == ("site_image_description",)
    assert caught.value.errors()[0]["type"] == "string_type"
    sdk[1].return_value = completion(json.dumps(data))
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 0)
    with pytest.raises(llm.LLMError):
        nodes.parse_and_check(create_initial_state("场地资料"))
    sdk[1].assert_called_once()


@pytest.mark.parametrize("suffix,data,mime", [(".png", b"\x89PNG\r\n\x1a\n", "image/png"),
                                             (".jpg", b"\xff\xd8\xff", "image/jpeg"),
                                             (".jpeg", b"\xff\xd8\xff", "image/jpeg")])
def test_multimodal_data_uri(sdk, tmp_path, suffix, data, mime):
    path = tmp_path / ("site" + suffix)
    path.write_bytes(data)
    llm.call_llm("图片任务", images=[str(path)])
    content = sdk[1].call_args.kwargs["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "图片任务"}
    uri = content[1]["image_url"]["url"]
    assert uri.startswith(f"data:{mime};base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == data


@pytest.mark.parametrize("failure", ["missing", "unsupported", "invalid", "unreadable"])
def test_controlled_image_errors_do_not_call_sdk(sdk, tmp_path, monkeypatch, failure):
    path = tmp_path / ("site.gif" if failure == "unsupported" else "site.png")
    if failure != "missing":
        path.write_bytes(b"invalid")
    if failure == "unreadable":
        from pathlib import Path
        monkeypatch.setattr(Path, "read_bytes", Mock(side_effect=PermissionError()))
    with pytest.raises(llm.LLMError):
        llm.call_llm("任务", images=[str(path)])
    sdk[0].assert_not_called()


def test_structured_output_is_pydantic_and_schema_is_in_json_constraint(sdk):
    sdk[1].return_value = completion(valid_vision().model_dump_json())
    output = llm.call_llm_structured("愿景", Vision)
    assert isinstance(output, Vision) and output == valid_vision()
    system = sdk[1].call_args.kwargs["messages"][0]["content"]
    assert "JSON" in system and "core_goal" in system


@pytest.mark.parametrize("bad", ["not JSON", '{"theme":"only"}', '{"theme":3}', "```json\n{}\n```"])
def test_parsing_or_pydantic_failure_retries_then_succeeds(sdk, bad):
    sdk[1].side_effect = [completion(bad), completion(valid_vision().model_dump_json())]
    assert llm.call_llm_structured("愿景", Vision) == valid_vision()
    assert sdk[1].call_count == 2


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_invalid_structured_output_has_finite_retry_and_controlled_error(sdk, monkeypatch, retries):
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", retries)
    sdk[1].return_value = completion('{"theme":"missing fields"}')
    with pytest.raises(llm.LLMError):
        llm.call_llm_structured("愿景", Vision)
    assert sdk[1].call_count == retries + 1
    assert llm.sleep.call_count == retries


def provider_error(kind):
    request = httpx.Request("POST", "https://example.invalid/chat")
    if kind == "network":
        return APIConnectionError(request=request)
    if kind == "timeout":
        return APITimeoutError(request=request)
    status = {"rate": 429, "server": 503, "auth": 401, "bad": 400}[kind]
    cls = {"rate": RateLimitError, "server": InternalServerError, "auth": AuthenticationError, "bad": BadRequestError}[kind]
    return cls("secret must not escape", response=httpx.Response(status, request=request), body={})


@pytest.mark.parametrize("kind", ["network", "timeout", "rate", "server"])
def test_transient_sdk_errors_retry(sdk, kind):
    sdk[1].side_effect = [provider_error(kind), completion("成功")]
    assert llm.call_llm("任务") == "成功"
    assert sdk[1].call_count == 2


@pytest.mark.parametrize("kind", ["auth", "bad"])
def test_permanent_sdk_errors_do_not_retry_or_leak(sdk, kind):
    sdk[1].side_effect = provider_error(kind)
    with pytest.raises(llm.LLMError) as caught:
        llm.call_llm("任务")
    assert "secret" not in str(caught.value)
    assert sdk[1].call_count == 1


def test_model_image_capability_failure_keeps_text_path_and_same_model(sdk, tmp_path):
    path = tmp_path / "site.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    sdk[1].side_effect = [provider_error("bad"), completion("文本路径成功")]
    with pytest.raises(llm.LLMError, match="图片"):
        llm.call_llm("图片", images=[str(path)])
    assert llm.call_llm("空间文字") == "文本路径成功"
    assert all(call.kwargs["model"] == config.LLM_MODEL for call in sdk[1].call_args_list)


@pytest.mark.parametrize("name,value", [("LLM_MODEL", ""), ("DASHSCOPE_API_KEY", ""),
                                      ("LLM_PROVIDER", "other"), ("LLM_BASE_URL", "invalid")])
def test_incomplete_config_is_controlled_before_sdk(sdk, monkeypatch, name, value):
    monkeypatch.setattr(config, name, value)
    with pytest.raises(llm.LLMError):
        llm.call_llm("任务")
    sdk[0].assert_not_called()


def test_empty_or_truncated_response_never_returns_illegal_data(sdk):
    sdk[1].side_effect = [completion(None), completion("partial", "length"), completion("valid")]
    assert llm.call_llm("任务") == "valid"
    assert sdk[1].call_count == 3


def test_prompt_loader_uses_files_and_serializes_input():
    prompt = llm.load_prompt("parse_input.md", "parse_and_check", {"user_input": "项目"})
    assert "输入解析与最低条件检查" in prompt
    assert json.loads(prompt.split("INPUT_JSON:\n")[1]) == {"user_input": "项目"}
    with pytest.raises(llm.LLMError):
        llm.load_prompt("../config.py", "task", {})


def test_llm_retry_does_not_increment_case_business_counter(sdk, monkeypatch, search_hit):
    from src.agent import nodes
    from src.agent.state import create_initial_state
    from src.skills import case_research
    from src.schemas import Case, CaseAnalysis, SiteAnalysis, SWOT
    site = SiteAnalysis(project_positioning="公共空间", location_conditions={}, functional_conditions={},
                        landscape_resources={}, public_space={}, transportation={}, spatial_conditions={},
                        swot=SWOT(strengths=[], weaknesses=[], opportunities=[], threats=[]), analysis_summary="公共节点")
    case = Case(name=search_hit["title"], location="未知", project_type="公共空间", source=search_hit["url"], relevance="分析推理")
    analysis = CaseAnalysis(case=case.name, relevance_reason="空间参考", spatial_strategy=["来源摘要空间连接"],
                            applicable_reference=["分析推理：节点联系"], limitations=["仅有摘要"])
    query_result = case_research._Queries(search_queries=["公共空间案例"])
    analyzed = case_research._CaseResults(filtered_cases=[case], case_analysis=[analysis])
    sdk[1].side_effect = [completion(query_result.model_dump_json()), provider_error("timeout"),
                          provider_error("timeout"), completion(analyzed.model_dump_json())]
    monkeypatch.setattr(case_research, "web_search", Mock(return_value=[search_hit]))
    state = create_initial_state("项目资料")
    state.update(site_analysis=site.model_dump(), research_direction=["公共空间"])
    before = dict(state)
    result = nodes.case_research(state)
    assert sdk[1].call_count == 4 and result["search_attempts"] == 1
    assert state == before


def test_llm_retry_and_concept_regeneration_are_separate(sdk, monkeypatch):
    from src.schemas import Concept, DesignOpportunity, SiteAnalysis, SWOT
    from src.skills import concept_generation
    from src.tools.image_generation import ImageGenerationError
    monkeypatch.setattr(concept_generation, "generate_image", Mock(side_effect=ImageGenerationError("离线图片失败")))
    site = SiteAnalysis(project_positioning="公共空间", location_conditions={}, functional_conditions={},
                        landscape_resources={}, public_space={}, transportation={}, spatial_conditions={},
                        swot=SWOT(strengths=[], weaknesses=[], opportunities=[], threats=[]), analysis_summary="公共节点")
    directions = concept_generation._OpportunitiesVision(
        opportunities=[DesignOpportunity(opportunity="连接节点", basis="公共节点", priority="high")], vision=valid_vision())
    concepts = concept_generation._Concepts(concepts=[
        Concept(name=name, core_concept=name, design_opportunities=["连接节点"], spatial_strategy=strategy,
                key_actions=[strategy], case_references=[])
        for name, strategy in [("路径联系", "组织连续路径"), ("公共节点", "组织开放节点")]])
    sdk[1].side_effect = [completion(directions.model_dump_json()), provider_error("timeout"),
                          completion(concepts.model_dump_json()), completion("FAIL 差异不够"),
                          provider_error("rate"), completion(concepts.model_dump_json()),
                          completion("路径空间意向"), completion("公共节点意向")]
    result = concept_generation.generate_concepts("项目资料", site.model_dump())
    assert sdk[1].call_count == 8
    assert len(result["concepts"]) == 2 and result["images"] == []
    tasks = [call.kwargs["messages"][1]["content"].split("当前任务：", 1)[1].split("\n", 1)[0]
             for call in sdk[1].call_args_list]
    assert tasks.count("quality_check") == 1
    assert tasks.count("generate_concepts") == tasks.count("regenerate_concepts") == 2
    assert tasks.count("image_prompt") == 2
    assert "quality_check" not in result
