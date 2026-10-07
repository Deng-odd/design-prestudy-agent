"""Source diagnostics must observe, never relax the production guard."""
import pytest

from conftest import make_site
from evals.dataset import load_dataset
from evals.run_eval import observe, run_case
from evals.source_diagnostics import compare_sources
from src.llm import LLMError
from src.schemas import Case, CaseAnalysis
from src.skills import case_research


@pytest.mark.parametrize("evidence_title,candidate_title,evidence_url,candidate_url,kind,title_equal,url_equal", [
    ("Shanghai&rsquo;s Xuhui Waterfront", "Shanghai’s Xuhui Waterfront", "https://example.com/a", "https://example.com/a", "representation_mismatch", True, True),
    ('City’s “Waterfront”', 'City\'s "Waterfront"', "https://example.com/a", "https://example.com/a", "representation_mismatch", True, True),
    ("Waterfront", "Waterfront", "https://example.com/a/", "https://example.com/a", "representation_mismatch", True, True),
    ("Waterfront", "Waterfront", "https://example.com/a", "https://wrong.example/other", "genuine_mismatch", True, False),
    ("Waterfront", "Waterfront", "https://example.com/a", "https://example.com/a", "exact_match", True, True),
])
def test_diagnostic_comparison_preserves_guard(fake_llm, monkeypatch, evidence_title, candidate_title,
                                              evidence_url, candidate_url, kind, title_equal, url_equal):
    candidate = Case(name=candidate_title, location="Not specified", project_type="Waterfront",
                     source=candidate_url, relevance="Research relevance")
    evidence = {"title": evidence_title, "url": evidence_url, "snippet": "Waterfront project", "source": "example.com"}
    result = case_research._CaseResults(filtered_cases=[candidate], case_analysis=[
        CaseAnalysis(case=candidate_title, relevance_reason="Research relevance", spatial_strategy=["Connect paths"],
                     applicable_reference=["Public access"], limitations=["Limited snippet"])
    ])
    monkeypatch.setattr(case_research, "web_search", lambda query: [evidence])
    monkeypatch.setattr(case_research, "_map_selected_cases", lambda *a, **k: result)
    row = compare_sources([candidate.model_dump()], [evidence])[0]
    assert row["classification"] == kind
    assert row["normalized_title_equal"] is title_equal
    assert row["normalized_url_equal"] is url_equal
    assert row["title_exact_match"] is (candidate_title == evidence_title)
    assert row["url_exact_match"] is (candidate_url == evidence_url)
    outcomes = []
    for instrumented in (False, True):
        def invoke():
            return case_research.research_cases(make_site().model_dump(), ["Waterfront"], ["query"])
        try:
            if instrumented:
                with observe(False, record_nodes=True):
                    value = invoke()
            else:
                value = invoke()
            outcomes.append(("pass", value))
        except LLMError as error:
            outcomes.append((type(error), str(error)))
    assert outcomes[0] == outcomes[1]
    assert (outcomes[0][0] == "pass") is (kind == "exact_match")


def test_failed_node_records_actual_candidate_and_evidence(fake_llm, sdk_search, monkeypatch):
    fake_llm.need_cases = True
    sdk_search.return_value = {"results": [{"title": "Shanghai&rsquo;s Xuhui Waterfront",
                                          "url": "https://example.com/a", "content": "Industrial waterfront"}]}
    original = case_research._map_selected_cases
    def candidate_response(selection, evidence):
        result = original(selection, evidence)
        if True:
            data = result.model_dump()
            data["filtered_cases"][0]["name"] = "Shanghai’s Xuhui Waterfront"
            data["case_analysis"][0]["case"] = "Shanghai’s Xuhui Waterfront"
            return case_research._CaseResults.model_validate(data)
        return result
    monkeypatch.setattr(case_research, "_map_selected_cases", candidate_response)
    result = run_case(load_dataset()[1], judge=False)
    failed = result["execution_trace"][-1]
    assert failed["node"] == "case_research" and failed["status"] == "failed"
    assert result["execution"]["failure_type"] == "source_consistency_validation"
    assert [entry["node"] for entry in result["execution_trace"]] == [
        "parse_and_check", "site_analysis", "check_case_need", "case_research"]
    row = failed["source_validation_diagnostics"][0]
    assert row["case_id"] == "case_02" and row["stage"] == "source_validation"
    assert row["candidate_index"] == row["matched_evidence_index"] == 0
    assert row["candidate_title"] == "Shanghai’s Xuhui Waterfront"
    assert row["evidence_title"] == "Shanghai&rsquo;s Xuhui Waterfront"
    assert row["title_exact_match"] is False and row["url_exact_match"] is True
    assert row["normalized_title_equal"] is True
    assert "html_entity" in row["title_diff_summary"]
    assert failed["tool_calls"]["search_calls"] >= 1
    assert result["decision_metrics"]["case_research_decision"]["score"] is True


def test_diagnostic_failure_cannot_change_guard_error(fake_llm, sdk_search, monkeypatch):
    from evals import source_diagnostics
    fake_llm.need_cases = True
    sdk_search.return_value = {"results": [{"title": "Evidence", "url": "https://example.com/a", "content": "Project"}]}
    original = case_research._map_selected_cases
    def candidate_response(selection, evidence):
        result = original(selection, evidence)
        if True:
            data = result.model_dump()
            data["filtered_cases"][0]["name"] = "Different title"
            return case_research._CaseResults.model_validate(data)
        return result
    monkeypatch.setattr(case_research, "_map_selected_cases", candidate_response)
    monkeypatch.setattr(source_diagnostics, "compare_sources", lambda *a: (_ for _ in ()).throw(ValueError("diagnostic failure")))
    result = run_case(load_dataset()[1], judge=False)
    assert result["execution"]["failure_type"] == "source_consistency_validation"
    assert result["execution_trace"][-1]["source_diagnostic_error"] == "ValueError"


def test_diagnostics_redact_credentials(monkeypatch):
    from src import config
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "actual-test-secret")
    candidate = Case(name="actual-test-secret", location="Unknown", project_type="Project",
                     source="https://user:password@example.com/a?token=secret", relevance="Relevant")
    row = compare_sources([candidate.model_dump()], [])[0]
    assert "actual-test-secret" not in str(row)
    assert "password" not in row["candidate_url"] and "=secret" not in row["candidate_url"]


@pytest.mark.parametrize("rewritten", [False, True])
def test_observation_keeps_graph_route_and_exception(fake_llm, sdk_search, monkeypatch, rewritten):
    from src.agent.graph import graph
    from src.agent.state import create_initial_state
    fake_llm.need_cases = True
    fake_llm.quality = ["PASS", "PASS"]
    sdk_search.return_value = {"results": [{"title": "Shanghai&rsquo;s Xuhui Waterfront",
                                          "url": "https://example.com/a", "content": "Industrial waterfront"}]}
    original = case_research._map_selected_cases
    def response(selection, evidence):
        result = original(selection, evidence)
        if rewritten:
            data = result.model_dump()
            data["filtered_cases"][0]["name"] = "Shanghai’s Xuhui Waterfront"
            data["case_analysis"][0]["case"] = "Shanghai’s Xuhui Waterfront"
            return case_research._CaseResults.model_validate(data)
        return result
    monkeypatch.setattr(case_research, "_map_selected_cases", response)
    from langchain_core.callbacks import BaseCallbackHandler
    class RouteRecorder(BaseCallbackHandler):
        def __init__(self):
            self.route = []
        def on_chain_start(self, serialized, inputs, *, metadata=None, **kwargs):
            node = (metadata or {}).get("langgraph_node")
            if node and kwargs.get("name") == node:
                self.route.append(node)
    outcomes = []
    for instrumented in (False, True):
        recorder = RouteRecorder()
        def invoke():
            graph.invoke(create_initial_state(load_dataset()[1].user_input), config={"callbacks": [recorder]})
        try:
            if instrumented:
                with observe(False, record_nodes=True):
                    invoke()
            else:
                invoke()
            outcomes.append((recorder.route, None))
        except LLMError as error:
            outcomes.append((recorder.route, (type(error), str(error))))
    assert outcomes[0] == outcomes[1]
    assert (outcomes[0][1] is None) is (not rewritten)
