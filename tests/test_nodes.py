from copy import deepcopy
from unittest.mock import Mock

import pytest
import requests

from src import config
from src.agent import nodes
from src.agent.state import create_initial_state
from src.agent.routes import route_info
from src.schemas import Case, CaseAnalysis, SiteAnalysis


def parsed_state():
    state = create_initial_state("滨水公共空间，北侧临道路")
    state.update(nodes.parse_and_check(state))
    state.update(nodes.site_analysis(state))
    return state


@pytest.mark.parametrize("sufficient", [True, False])
@pytest.mark.parametrize("images", [None, ["site.png"]])
def test_parse_partial_update_and_images(fake_llm, sufficient, images):
    fake_llm.sufficient = sufficient
    state = create_initial_state("项目资料", images)
    before = deepcopy(state)
    result = nodes.parse_and_check(state)
    assert result["info_sufficient"] is sufficient
    assert bool(result["missing_critical"]) is not sufficient
    assert result["missing_optional"]
    assert bool(result["followup_question"]) is not sufficient
    assert set(result) == set(nodes._ParsedInput.model_fields)
    assert state == before
    assert result["site_image_description"] == ("图片显示场地空间" if images else "")
    task, inputs, kwargs = fake_llm.calls[0]
    assert task == "parse_and_check" and inputs == {"user_input": "项目资料"}
    assert kwargs["images"] == state["site_images"]
    assert kwargs["temperature"] == config.LLM_TEMPERATURE_DECISION


def test_ask_user_is_read_only_and_never_calls_llm(fake_llm):
    state = create_initial_state("资料不足")
    before = deepcopy(state)
    assert nodes.ask_user(state) == {}
    assert state == before and fake_llm.calls == []


def test_site_node_returns_only_validated_site_analysis(fake_llm):
    state = create_initial_state("项目资料")
    state.update(nodes.parse_and_check(state))
    result = nodes.site_analysis(state)
    assert set(result) == {"site_analysis"}
    SiteAnalysis.model_validate(result["site_analysis"])


@pytest.mark.parametrize("needed", [True, False])
def test_check_case_need_only_decides(fake_llm, monkeypatch, needed):
    fake_llm.need_cases = needed
    search = Mock(side_effect=AssertionError("不应搜索"))
    monkeypatch.setattr(nodes, "research_cases", search)
    state = parsed_state()
    before = deepcopy(state)
    result = nodes.check_case_need(state)
    assert result["need_case_research"] is needed
    assert set(result) == {"need_case_research", "research_direction"}
    assert state == before
    search.assert_not_called()
    assert fake_llm.calls[-1][2]["temperature"] == config.LLM_TEMPERATURE_DECISION


@pytest.mark.parametrize("attempts", [0, 1])
def test_case_node_increments_once_and_does_not_mutate(fake_llm, monkeypatch, attempts):
    fake_llm.need_cases = True
    state = parsed_state()
    state.update(nodes.check_case_need(state))
    state["search_attempts"] = attempts
    mock = Mock(wraps=nodes.research_cases)
    monkeypatch.setattr(nodes, "research_cases", mock)
    before = deepcopy(state)
    result = nodes.case_research(state)
    mock.assert_called_once()
    assert result["search_attempts"] == attempts + 1
    assert set(result) == {"search_queries", "filtered_cases", "case_analysis", "search_attempts"}
    assert state == before


@pytest.mark.parametrize("sufficient", [True, False])
def test_check_research_only_updates_decision(fake_llm, sufficient):
    fake_llm.research_checks = [sufficient]
    state = parsed_state()
    before = deepcopy(state)
    result = nodes.check_research(state)
    assert result["research_sufficient"] is sufficient
    assert bool(result["research_gaps"]) is not sufficient
    assert set(result) == {"research_sufficient", "research_gaps"}
    assert state == before


def test_refine_search_does_not_gate_on_attempt_count(fake_llm):
    state = {"research_gaps": ["空间联系"], "search_queries": ["公共空间"], "research_direction": ["慢行"], "search_attempts": 2}
    before = deepcopy(state)
    result = nodes.refine_search(state)
    assert result == {"search_queries": ["公共空间 慢行联系 设计案例"]}
    assert state == before
    assert "search_attempts" not in fake_llm.calls[-1][1]


def test_concept_and_report_nodes_only_update_owned_fields(fake_llm):
    state = parsed_state()
    concepts = nodes.concept_generation(state)
    assert set(concepts) == {"opportunities", "vision", "concepts", "images"}
    state.update(concepts)
    before = deepcopy(state)
    report = nodes.report_composition(state)
    assert set(report) == {"final_report"} and report["final_report"].startswith("#")
    assert state == before


def test_tool_retries_only_increment_one_business_attempt(fake_llm, sdk_search, search_hit):
    sdk_search.side_effect = [requests.Timeout(), requests.Timeout(), {"results": [
        {"title": search_hit["title"], "url": search_hit["url"], "content": search_hit["snippet"], "score": .9}]}]
    fake_llm.need_cases = True
    state = parsed_state()
    state.update(nodes.check_case_need(state))
    before = deepcopy(state)
    result = nodes.case_research(state)
    assert sdk_search.call_count == 3 and result["search_attempts"] == 1
    assert state == before
    Case.model_validate(result["filtered_cases"][0])
    CaseAnalysis.model_validate(result["case_analysis"][0])


def test_tool_exhaustion_still_counts_one_business_attempt(fake_llm, sdk_search):
    sdk_search.side_effect = requests.ConnectionError()
    fake_llm.need_cases = True
    state = parsed_state()
    state.update(nodes.check_case_need(state))
    result = nodes.case_research(state)
    state.update(result)
    assert sdk_search.call_count == 3 and result["search_attempts"] == 1
    assert result["filtered_cases"] == result["case_analysis"] == []
    assert not nodes.check_research(state)["research_sufficient"]


@pytest.mark.parametrize(
    "user_input,sufficient,critical,optional,instruction_fragments",
    [
        ("帮我做一个城市设计方案。", False, ["研究对象与基本场地空间条件"], [],
         ["无法识别研究对象", "几乎没有可分析", "不能仅凭项目类型或笼统目标放行"]),
        ("滨水旧仓储区更新，北侧河流，南侧道路，现状岸线封闭，希望开放公共空间。",
         True, [], ["城市名称"], ["城市名称", "不得以“更准确”为由升级为 critical"]),
        ("40 公顷片区更新，东侧轨道站、西侧公园，住宅与商业混合，公共空间零散；希望改善连接，FAR 和高度未定。",
         True, [], ["FAR/容积率", "建筑高度"], ["FAR/容积率", "建筑高度", "不能编造未提供的指标"]),
        ("旧产业园更新，厂房和仓储密集，内部道路封闭，希望保留生产并增加研发与公共空间，没有 CAD 或红线图。",
         True, [], ["CAD/总平图", "完整用地红线"], ["CAD/总平图", "完整用地红线", "已有充分文字空间描述时不要求图片"]),
        ("TOD 更新：站点位于场地中部，东侧是公园，西侧高密度街区，南北向主干道形成分隔，希望改善步行联系。",
         True, [], ["精确地址/经纬度"], ["相对空间信息可以替代绝对定位", "不需要先知道城市名或坐标"]),
        ("同一个研究对象既被定义为完全没有任何建筑的自然湿地，又被明确要求只研究该对象现有的密集办公建筑；两种现状描述都必须视为准确且不能区分子区域。",
         False, ["确认互相矛盾的研究对象现状"], [], ["核心信息存在严重矛盾", "不把可共同存在的多功能或多约束误判为矛盾"]),
        ("准备做一个 CBD 更新项目，希望提升品质与活力，请做前期研究和设计方向。",
         False, ["实际场地范围/研究对象", "现状空间条件或具体问题"], [],
         ["做一个 CBD 更新，提升品质与活力", "没有实际场地范围/研究对象"]),
    ],
    ids=["truly-insufficient", "no-city", "no-far-height", "no-cad-boundary",
         "relative-location", "contradictory-core", "generic-cbd-insufficient"],
)
def test_parse_preliminary_research_prompt_and_decision_contract(
    monkeypatch, user_input, sufficient, critical, optional, instruction_fragments
):
    """离线验证真实 Prompt 传递与判断契约；mock 不证明模型语义判断效果。"""
    import json

    expected = nodes._ParsedInput(
        project_background=user_input, location="", planning_conditions={},
        client_requirements=None, site_image_description="", info_sufficient=sufficient,
        missing_critical=critical, missing_optional=optional,
        followup_question="请补充：" + "、".join(critical) if critical else "",
    )

    def structured(prompt, schema, **kwargs):
        assert schema is nodes._ParsedInput
        assert "不是判断是否足以完成正式规划、详细设计或审批" in prompt
        assert "最后一种情况须说明为什么已有资料不能支持前期研究" in prompt
        assert "不把这些字段规定为永远 optional" in prompt
        for fragment in instruction_fragments:
            assert fragment in prompt
        assert json.loads(prompt.split("INPUT_JSON:\n", 1)[1]) == {"user_input": user_input}
        assert kwargs["images"] == []
        assert kwargs["temperature"] == config.LLM_TEMPERATURE_DECISION
        return schema.model_validate(expected.model_dump())

    llm = Mock(side_effect=structured)
    monkeypatch.setattr(nodes, "call_llm_structured", llm)
    state = create_initial_state(user_input)
    before = deepcopy(state)
    update = nodes.parse_and_check(state)
    llm.assert_called_once()
    assert state == before
    assert set(update) == set(nodes._ParsedInput.model_fields)
    assert update["missing_critical"] == critical
    assert update["missing_optional"] == optional
    assert update["info_sufficient"] is sufficient
    assert update["site_image_description"] == ""
    assert bool(update["followup_question"]) is not sufficient
    state.update(update)
    assert route_info(state) == ("site_analysis" if sufficient else "ask_user")
    if not sufficient:
        assert nodes.ask_user(state) == {}
        llm.assert_called_once()
