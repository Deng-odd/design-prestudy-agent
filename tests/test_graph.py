from copy import deepcopy
from unittest.mock import Mock

import pytest
import requests

from src import config
from src.agent.graph import build_graph, graph
from src.agent.state import AgentState, create_initial_state
from src.schemas import Case, CaseAnalysis, Concept, GeneratedImage, SiteAnalysis, Vision
from src.skills import case_research
from src.tools.web_search import WebSearchError


@pytest.mark.parametrize("path,rounds", [("A", []), ("B", []), ("C", [True]),
                                        ("D_sufficient", [False, True]), ("D_insufficient", [False, False])])
def test_all_paths_and_both_second_round_exits(monkeypatch, fake_llm, fake_image, search_hit, path, rounds):
    fake_llm.sufficient = path != "A"
    fake_llm.need_cases = bool(rounds)
    search = Mock(side_effect=[[search_hit] if sufficient else [] for sufficient in rounds])
    monkeypatch.setattr(case_research, "web_search", search)
    initial = create_initial_state("滨水公共空间，北侧临道路")
    before = deepcopy(initial)
    updates = list(build_graph().stream(initial, stream_mode="updates", config={"recursion_limit": 20}))
    visited = [name for update in updates for name in update]
    expected = ["parse_and_check", "ask_user"] if path == "A" else ["parse_and_check", "site_analysis", "check_case_need"]
    for index in range(len(rounds)):
        if index:
            expected.append("refine_search")
        expected += ["case_research", "check_research"]
    if path != "A":
        expected += ["concept_generation", "report_composition"]
    assert visited == expected
    assert search.call_count == len(rounds) <= 2
    assert initial == before
    state = deepcopy(initial)
    for update in updates:
        for partial in update.values():
            assert set(partial or {}) <= AgentState.__annotations__.keys()
            state.update(partial or {})
    assert state["search_attempts"] == len(rounds)
    assert "quality_check" not in state
    if path == "A":
        assert state["followup_question"] and "final_report" not in state
        fake_image.assert_not_called()
    else:
        assert state["final_report"].startswith("#")
        SiteAnalysis.model_validate(state["site_analysis"])
        Vision.model_validate(state["vision"])
        for item in state["concepts"]:
            Concept.model_validate(item)
        assert fake_image.call_count == len(state["images"]) == len(state["concepts"])
        for image in state["images"]:
            GeneratedImage.model_validate(image)
            assert f"![{image['concept_name']}]({image['image_url']})" in state["final_report"]
        assert fake_llm.calls[-1][1]["images"] == state["images"]
        for item in state.get("filtered_cases", []):
            Case.model_validate(item)
        for item in state.get("case_analysis", []):
            CaseAnalysis.model_validate(item)
        if rounds:
            assert state["research_sufficient"] is rounds[-1]


def test_compile_has_exactly_nine_business_nodes_and_no_checkpointer():
    assert set(graph.get_graph().nodes) - {"__start__", "__end__"} == {
        "parse_and_check", "ask_user", "site_analysis", "check_case_need", "case_research",
        "check_research", "refine_search", "concept_generation", "report_composition"}
    assert graph.checkpointer is None
    assert any(edge.source == "ask_user" and edge.target == "__end__" for edge in graph.get_graph().edges)


def test_missing_credentials_graph_finishes_after_two_empty_rounds(fake_llm):
    fake_llm.need_cases = True
    state = graph.invoke(create_initial_state("滨水公共空间，北侧临道路"))
    assert state["search_attempts"] == 2 and state["research_sufficient"] is False
    assert state["images"] == [] and state["final_report"]


def test_tool_failures_are_bounded_separately_from_business_rounds(fake_llm, sdk_search):
    fake_llm.need_cases = True
    sdk_search.side_effect = requests.Timeout()
    state = graph.invoke(create_initial_state("滨水公共空间，北侧临道路"), config={"recursion_limit": 20})
    assert sdk_search.call_count == 2 * (config.TOOL_MAX_RETRIES + 1)
    assert state["search_attempts"] == 2 and not state["research_sufficient"]
    assert state["final_report"] and set(state) <= AgentState.__annotations__.keys()


def test_graph_concept_regeneration_is_internal_and_once(fake_llm):
    fake_llm.quality = ["FAIL 策略重复"]
    state = graph.invoke(create_initial_state("滨水公共空间，北侧临道路"))
    assert fake_llm.generation_count == 2
    assert [task for task, _, _ in fake_llm.calls].count("quality_check") == 1
    assert state["final_report"] and "quality_check" not in state
