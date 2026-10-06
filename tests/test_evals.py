"""Offline evaluation infrastructure validation; never a baseline."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from evals.dataset import ROOT, EvalCase, load_dataset
from evals.judge import JudgeScore, applicable, judge_metric, output_available
from evals.metrics import aggregate, average, metric, rule_metrics
from evals.run_eval import failure_type, images_enabled, main, observe, run_case


def test_frozen_dataset_and_asset():
    cases = load_dataset()
    assert len(cases) == len({c.case_id for c in cases}) == 10
    assert {c.dataset_version for c in cases} == {"1.0"}
    assert cases[1].site_images == ["data/eval/assets/case_02_tod_site.png"]
    asset = ROOT / cases[1].site_images[0]
    assert asset.read_bytes() == Path(str(asset) + ".png").read_bytes()
    assert cases[2].expected_info_sufficient is False
    assert cases[4].expected_need_case_research is False
    assert cases[8].expected_need_case_research is None
    assert "source_consistency_validation" in cases[6].notes
    assert "expected_search_attempts" not in cases[6].model_dump()


@pytest.mark.parametrize("field,value", [("site_images", ["../outside.png"]), ("site_images", ["C:/secret.png"]), ("site_images", ["data/input.pdf"]), ("image_generation_mode", "never"), ("dataset_version", "1.1")])
def test_dataset_schema_rejects_invalid(field, value):
    data = load_dataset()[0].model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        EvalCase.model_validate(data)


def test_na_denominator():
    assert average([metric(4), metric(None, applicable=False), metric(None)]) == {"average": 4, "valid_cases": 1}
    assert average([metric(None, applicable=False)])["average"] is None


@pytest.mark.parametrize("score", [0, 6, True, "4"])
def test_judge_score_bounds(score):
    with pytest.raises(ValidationError):
        JudgeScore(score=score, reason="reason", key_issues=[])


def test_judge_uses_public_llm_and_na_skips(monkeypatch):
    from evals import judge
    llm = Mock(return_value=JudgeScore(score=4, reason="符合条件", key_issues=[]))
    monkeypatch.setattr(judge, "call_llm_structured", llm)
    case = load_dataset()[0]
    from conftest import make_site
    result = judge_metric(case, {"site_analysis": make_site().model_dump()}, "site_analysis", evidence=[{"source": "example.com"}])
    assert result["score"] == 4
    assert "expected_points" in llm.call_args.args[0]
    judge_metric(load_dataset()[2], {}, "site_analysis")
    assert llm.call_count == 1
    assert not applicable(load_dataset()[1], "site_analysis", vision_supported=False)


@pytest.mark.parametrize("index,on,off", [(0, True, False), (1, False, False), (9, True, True)])
def test_image_policy(index, on, off):
    case = load_dataset()[index]
    assert images_enabled(case, "on") is on
    assert images_enabled(case, "off") is off


def test_runner_actual_graph_images_disabled_and_restored(fake_llm, fake_image):
    from src.skills import concept_generation
    original = concept_generation.generate_image
    case = load_dataset()[0]
    result = run_case(case, judge=False)
    assert result["execution"]["status"] == "success"
    assert result["agent_output"]["concepts"] and result["agent_output"]["final_report"]
    assert result["agent_output"]["images"] == []
    assert result["execution"]["image_calls"] == 0
    assert not any(task == "image_prompt" for task, _, _ in fake_llm.calls)
    fake_image.assert_not_called()
    assert concept_generation.generate_image is original
    assert result["decision_metrics"]["info_sufficiency_decision"]["score"] is True
    assert result["decision_metrics"]["case_research_decision"]["score"] is False
    assert result["quality_metrics"]["site_analysis"]["applicable"]


def test_required_calls_image_and_regeneration_once(fake_llm, fake_image):
    fake_llm.quality = ["FAIL 重复"]
    result = run_case(load_dataset()[9], images="off", judge=False)
    assert fake_image.call_count == 2
    assert len(result["agent_output"]["images"]) == 2
    assert result["execution"]["concept_regenerations"] == 1
    assert result["decision_metrics"]["workflow_compliance"]["concept_regeneration_limit"]["score"]


def test_ask_user_quality_na(fake_llm):
    fake_llm.sufficient = False
    result = run_case(load_dataset()[2])
    assert result["execution"]["status"] == "success"
    assert result["decision_metrics"]["info_sufficiency_decision"]["score"]
    assert all(not v["applicable"] for v in result["quality_metrics"].values())


def test_input_images_retained_when_generation_disabled(fake_llm):
    result = run_case(load_dataset()[1], judge=False)
    assert result["agent_output"]["site_images"] == [str(ROOT / "data/eval/assets/case_02_tod_site.png")]
    parse = next(kwargs for task, _, kwargs in fake_llm.calls if task == "parse_and_check")
    assert parse["images"] == result["agent_output"]["site_images"]


def test_failed_source_logged_without_fix(fake_llm, monkeypatch):
    from src.agent import nodes
    from src.llm import LLMError
    original = nodes.call_llm_structured
    def broken(prompt, schema, **kwargs):
        if "当前任务：check_case_need\n" in prompt:
            raise LLMError("案例来源或标题不属于检索证据")
        return original(prompt, schema, **kwargs)
    monkeypatch.setattr(nodes, "call_llm_structured", broken)
    result = run_case(load_dataset()[6], judge=False)
    assert result["execution"]["failure_type"] == "source_consistency_validation"
    assert result["execution"]["status"] == "failed"
    assert result["quality_metrics"]["case_research"]["applicable"]
    assert result["quality_metrics"]["case_research"]["score"] is None


def test_workflow_limits_and_runtime_aggregation(fake_llm):
    result = run_case(load_dataset()[0], judge=False)
    changed = deepcopy(result)
    changed["agent_output"]["search_attempts"] = 3
    changed["execution"]["concept_regenerations"] = 2
    rules = rule_metrics(load_dataset()[0], changed["agent_output"], changed["execution_trace"], changed["execution"])
    assert not rules["workflow_compliance"]["search_limit"]["score"]
    assert not rules["workflow_compliance"]["concept_regeneration_limit"]["score"]
    result["execution"]["runtime_seconds"] = 1
    changed["execution"].update(runtime_seconds=3, status="failed", failure_type="llm_call_or_validation")
    summary = aggregate([result, changed])
    assert summary["C_operational"]["runtime_median"] == 2
    assert summary["C_operational"]["runtime_p95"] == 3
    assert summary["C_operational"]["failure_rate"] == .5
    assert "overall_score" not in summary


def test_sdk_calls_retry_count_tokens(monkeypatch):
    from openai.resources.chat.completions import Completions
    from openai.resources.images import Images
    from tavily import TavilyClient
    response = SimpleNamespace(usage=SimpleNamespace(total_tokens=25))
    monkeypatch.setattr(Completions, "create", Mock(side_effect=[RuntimeError("temporary"), response]))
    monkeypatch.setattr(Images, "generate", Mock(return_value=SimpleNamespace(data=[])))
    monkeypatch.setattr(TavilyClient, "search", Mock(return_value={"results": []}))
    with observe(True) as stats:
        with pytest.raises(RuntimeError):
            Completions.create()
        Completions.create()
        Images.generate()
        TavilyClient.search()
    assert (stats["llm_calls"], stats["image_calls"], stats["search_calls"]) == (2, 1, 1)
    assert stats["tokens"] is None  # Failed request usage is unknown, not zero.
    assert stats["cost"] is None


def test_cli_single_case_saves_results(tmp_path, fake_llm):
    directory = tmp_path / "run"
    main(["--case", "case_05", "--no-judge", "--output", str(directory)])
    assert (directory / "case_05.json").is_file()
    assert (directory / "summary.json").is_file()
    assert not (directory / "case_01.json").exists()


def test_failed_case_node_preserves_queries_evidence_calls_and_decision(fake_llm, sdk_search, search_hit, monkeypatch):
    from src.skills import case_research
    from src.schemas import Case
    fake_llm.need_cases = True
    sdk_search.return_value = {"results": [{"title": search_hit["title"], "url": search_hit["url"], "content": search_hit["snippet"]}]}
    original = case_research.call_llm_structured
    def changed_title(prompt, schema, **kwargs):
        result = original(prompt, schema, **kwargs)
        if "当前任务：analyze_cases\n" in prompt:
            data = result.model_dump()
            data["filtered_cases"][0] = Case.model_validate({**data["filtered_cases"][0], "name": "改写后的标题"}).model_dump()
            return schema.model_validate(data)
        return result
    monkeypatch.setattr(case_research, "call_llm_structured", changed_title)
    result = run_case(load_dataset()[6], judge=False)
    assert result["execution"]["status"] == "failed"
    assert result["execution"]["failure_type"] == "source_consistency_validation"
    failed = result["execution_trace"][-1]
    assert failed["node"] == "case_research" and failed["status"] == "failed"
    assert failed["failure_type"] == "source_consistency_validation"
    assert failed["error"] == "案例来源或标题不属于检索证据"
    assert failed["search_queries"] == ["公共空间 设计案例"]
    assert failed["search_observations"][0]["query"] == failed["search_queries"][0]
    assert failed["search_observations"][0]["results"][0]["url"] == search_hit["url"]
    assert failed["retrieval_evidence"][0]["title"] == search_hit["title"]
    assert failed["tool_calls"]["search_calls"] == result["execution"]["search_calls"] == 1
    assert result["agent_output"]["search_attempts"] == 0
    assert result["decision_metrics"]["case_research_decision"]["score"] is True
    assert result["decision_metrics"]["info_sufficiency_decision"]["score"] is True
    assert not result["decision_metrics"]["workflow_compliance"]["completion"]["score"]
    assert all(e["status"] == "success" for e in result["execution_trace"][:-1])
    assert failed["update"] == {}  # Observation is not an Agent State update.


@pytest.mark.parametrize("enough,fail_task", [(True, "opportunities_and_vision"), (False, "refine_search")])
def test_research_decision_not_overridden_by_downstream_failure(fake_llm, sdk_search, search_hit, monkeypatch, enough, fail_task):
    from src.agent import nodes
    from src.skills import concept_generation
    from src.llm import LLMError
    fake_llm.need_cases = True
    fake_llm.research_checks = [enough]
    sdk_search.return_value = {"results": [{"title": search_hit["title"], "url": search_hit["url"], "content": search_hit["snippet"]}]}
    module = concept_generation if enough else nodes
    original = module.call_llm_structured
    def fail_downstream(prompt, schema, **kwargs):
        if "当前任务：" + fail_task + "\n" in prompt:
            raise LLMError("LLM 调用或输出校验最终失败")
        return original(prompt, schema, **kwargs)
    monkeypatch.setattr(module, "call_llm_structured", fail_downstream)
    result = run_case(load_dataset()[6], judge=False)
    assert result["execution"]["status"] == "failed"
    assert result["execution_trace"][-1]["status"] == "failed"
    assert result["decision_metrics"]["research_sufficiency_decision"]["score"] is True
    assert result["decision_metrics"]["case_research_decision"]["score"] is True


def test_info_decision_independent_of_ask_user_failure():
    state = {"info_sufficient": False, "search_attempts": 0}
    trace = [{"node": "parse_and_check", "status": "success", "update": state, "state": state},
             {"node": "ask_user", "status": "failed", "update": {}, "state": state}]
    result = rule_metrics(load_dataset()[2], state, trace, {"status": "failed", "concept_regenerations": 0})
    assert result["info_sufficiency_decision"]["score"] is True
    assert result["workflow_compliance"]["completion"]["score"] is False


def test_unproduced_decision_is_unavailable_not_incorrect():
    trace = [{"node": "check_research", "status": "failed", "update": {}, "state": {}}]
    result = rule_metrics(load_dataset()[6], {}, trace, {"status": "failed"})
    for key in ("info_sufficiency_decision", "case_research_decision", "research_sufficiency_decision"):
        assert result[key]["applicable"] and result[key]["score"] is None


@pytest.mark.parametrize("index,expected", [
    (3, ["n/a", "unavailable", "unavailable", "unavailable", "n/a"]),
    (4, ["n/a", "n/a", "n/a", "unavailable", "n/a"]),
    (9, ["unavailable"] * 5),
    (2, ["n/a"] * 5),
])
def test_early_stop_quality_status_and_no_judge(fake_llm, monkeypatch, index, expected):
    from evals import judge
    fake_llm.sufficient = False
    llm = Mock(side_effect=AssertionError("No professional output: Judge must not run"))
    monkeypatch.setattr(judge, "call_llm_structured", llm)
    result = run_case(load_dataset()[index])
    assert [entry["status"] for entry in result["quality_metrics"].values()] == expected
    assert all(entry["score"] is None for entry in result["quality_metrics"].values())
    assert [e["node"] for e in result["execution_trace"]] == ["parse_and_check", "ask_user"]
    llm.assert_not_called()


@pytest.mark.parametrize("index", [1, 5])
def test_failed_execution_still_scores_saved_professional_outputs(fake_llm, sdk_search, search_hit, monkeypatch, index):
    from evals import judge
    from src.skills import case_research
    from src.agent import nodes
    from src.llm import LLMError
    fake_llm.need_cases = True
    fake_llm.research_checks = [False]
    sdk_search.return_value = {"results": [{"title": search_hit["title"], "url": search_hit["url"], "content": search_hit["snippet"]}]}
    llm = Mock(return_value=JudgeScore(score=4, reason="Evaluate existing professional facts only", key_issues=[]))
    monkeypatch.setattr(judge, "call_llm_structured", llm)
    if index == 1:
        original = case_research.call_llm_structured
        def fail(prompt, schema, **kwargs):
            if "当前任务：analyze_cases\n" in prompt:
                raise LLMError("案例来源或标题不属于检索证据")
            return original(prompt, schema, **kwargs)
        monkeypatch.setattr(case_research, "call_llm_structured", fail)
    else:
        original = nodes.call_llm_structured
        def fail(prompt, schema, **kwargs):
            if "当前任务：refine_search\n" in prompt:
                raise LLMError("LLM 调用或输出校验最终失败")
            return original(prompt, schema, **kwargs)
        monkeypatch.setattr(nodes, "call_llm_structured", fail)
    result = run_case(load_dataset()[index])
    assert result["execution"]["status"] == "failed"
    assert result["agent_output"]["site_analysis"]
    for name in ("site_analysis", "groundedness"):
        assert result["quality_metrics"][name]["status"] == "scored"
        assert result["quality_metrics"][name]["score"] == 4
    assert llm.call_count == 2
    if index == 5:
        assert result["agent_output"]["case_analysis"]
        # Case 06 does not select Case Research quality; test it with Case 04's frozen focus.
        result = judge_metric(load_dataset()[3], result["agent_output"], "case_research")
        assert result["status"] == "scored" and llm.call_count == 3


def test_availability_is_content_based_and_e2e_requires_chain(fake_llm):
    from conftest import make_site
    from src.schemas import Concept, DesignOpportunity
    case = load_dataset()[9]
    concepts = [Concept(name="Direction", core_concept="Connected nodes", design_opportunities=["Connectivity"],
                        spatial_strategy="Link public nodes", key_actions=["Connect paths"], case_references=[]).model_dump()]
    opportunity = DesignOpportunity(opportunity="Connectivity", basis="Disconnected paths", priority="high").model_dump()
    for state in ({}, {"site_analysis": {}}, {"concepts": []}, {"final_report": "  "}, {"project_background": "Input summary"}):
        assert not output_available(case, state, "groundedness")
    state = {"site_analysis": make_site().model_dump(), "opportunities": [opportunity], "concepts": concepts, "final_report": "# Report"}
    assert output_available(case, state, "site_analysis")
    assert output_available(case, state, "groundedness")
    assert output_available(case, state, "concept_quality")
    assert not output_available(case, state, "case_research")
    assert not output_available(case, state, "end_to_end_usability")
    assert output_available(load_dataset()[4], state, "end_to_end_usability")  # Research not required.


def test_real_output_can_receive_one_but_unavailable_cannot(monkeypatch):
    from conftest import make_site
    from evals import judge
    llm = Mock(return_value=JudgeScore(score=1, reason="Actual analysis is generic", key_issues=["Generic content"]))
    monkeypatch.setattr(judge, "call_llm_structured", llm)
    case = load_dataset()[0]
    missing = judge_metric(case, {}, "site_analysis")
    assert missing["status"] == "unavailable" and missing["applicable"] and missing["score"] is None
    llm.assert_not_called()
    scored = judge_metric(case, {"site_analysis": make_site().model_dump()}, "site_analysis")
    assert scored["status"] == "scored" and scored["score"] == 1
    assert llm.call_count == 1
    assert "缺失应有输出时依 Rubric 评分" not in llm.call_args.args[0]
    assert average([scored, missing, {**metric(None, applicable=False), "status": "n/a"}]) == {"average": 1, "valid_cases": 1}
    assert average([{**metric(1), "status": "unavailable"}])["valid_cases"] == 0


def test_judge_failure_continues_metrics_and_preserves_agent_status(fake_llm, monkeypatch):
    from evals import judge
    from src.llm import LLMError
    called = []
    def judge_response(prompt, schema, **kwargs):
        data = json.loads(prompt.split("\n", 1)[1])
        called.append(data["metric"])
        if data["metric"] == "groundedness":
            raise LLMError("LLM 调用或输出校验最终失败")
        return JudgeScore(score=4, reason="Actual output evaluated", key_issues=[])
    monkeypatch.setattr(judge, "call_llm_structured", judge_response)
    result = run_case(load_dataset()[0])
    assert result["execution"]["status"] == "success"
    assert result["execution"]["failure_type"] is None
    assert result["quality_metrics"]["site_analysis"]["status"] == "scored"
    assert result["quality_metrics"]["concept_quality"]["status"] == "scored"
    failed = result["quality_metrics"]["groundedness"]
    assert failed["status"] == "unavailable" and failed["score"] is None
    assert failed["failure_stage"] == "judge" and failed["metric"] == "groundedness"
    assert failed["failure_type"] == "llm_call_or_validation"
    assert failed["exception_type"] == "LLMError" and failed["error"] == "LLMError: llm_call_or_validation"
    assert called == ["site_analysis", "groundedness", "concept_quality"]
    assert result["judge_failures"][0]["error"] == failed["error"]
    summary = aggregate([result])
    assert summary["C_operational"]["failure_rate"] == 0
    assert summary["B_quality"]["groundedness"]["valid_cases"] == 0


def test_judge_failure_does_not_stop_subsequent_cli_case(fake_llm, monkeypatch, tmp_path):
    from evals import judge
    from src.llm import LLMError
    fake_llm.quality = ["PASS", "PASS"]  # One actual concept quality check per Case.
    called = []
    def response(prompt, schema, **kwargs):
        data = json.loads(prompt.split("\n", 1)[1])
        case_id = data["ground_truth"]["case_id"]
        called.append((case_id, data["metric"]))
        if case_id == "case_01" and data["metric"] == "groundedness":
            raise LLMError("LLM 调用或输出校验最终失败")
        return JudgeScore(score=4, reason="Saved professional output", key_issues=[])
    monkeypatch.setattr(judge, "call_llm_structured", response)
    directory = tmp_path / "judge-continue"
    main(["--case", "case_01", "--case", "case_08", "--output", str(directory)])
    first = json.loads((directory / "case_01.json").read_text(encoding="utf-8"))
    second = json.loads((directory / "case_08.json").read_text(encoding="utf-8"))
    assert first["judge_failures"] and first["execution"]["status"] == "success"
    assert not second["judge_failures"] and second["execution"]["status"] == "success"
    assert second["quality_metrics"]["groundedness"]["status"] == "scored"
    assert ("case_08", "concept_quality") in called
    assert json.loads((directory / "summary.json").read_text(encoding="utf-8"))["C_operational"]["failure_rate"] == 0
