from copy import deepcopy
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from src import config
from src.llm import LLMError
from src.schemas import Case, CaseAnalysis, Concept, DesignOpportunity, GeneratedImage, SiteAnalysis, Vision
from src.tools.image_generation import ImageGenerationError
from src.skills import case_research, concept_generation, report_composition, site_analysis
from src.tools.web_search import WebSearchError


def site_data():
    return site_analysis.analyze_site("滨水公共空间，北侧临道路", "示例城市")["site_analysis"]


@pytest.mark.parametrize("images", [None, ["site.png"]])
def test_site_analysis_validates_with_or_without_images(fake_llm, images):
    result = site_analysis.analyze_site("项目定位与空间文字", "示例城市", site_images=images)
    site = SiteAnalysis.model_validate(result["site_analysis"])
    assert set(result) == {"site_analysis"} and site.swot.strengths
    assert fake_llm.calls[-1][0] == "site_analysis"
    assert fake_llm.calls[-1][2] == {"images": images, "temperature": config.LLM_TEMPERATURE_ANALYSIS}
    assert fake_llm.calls[-1][1]["project_background"] == "项目定位与空间文字"


def test_case_research_validated_mock_and_no_counter(fake_llm, monkeypatch, search_hit):
    search = Mock(return_value=[search_hit])
    monkeypatch.setattr(case_research, "web_search", search)
    site = site_data()
    before = deepcopy(site)
    result = case_research.research_cases(site, ["公共空间"])
    assert set(result) == {"search_queries", "filtered_cases", "case_analysis"}
    Case.model_validate(result["filtered_cases"][0])
    CaseAnalysis.model_validate(result["case_analysis"][0])
    assert site == before
    search.assert_called_once_with(result["search_queries"][0])
    task, inputs, kwargs = fake_llm.calls[-1]
    assert task == "analyze_cases" and inputs["search_results"] == [{**search_hit, "source_id": "src_001"}]
    assert kwargs["temperature"] == config.LLM_TEMPERATURE_ANALYSIS


def test_current_queries_are_consumed_without_new_round(fake_llm, monkeypatch, search_hit):
    search = Mock(return_value=[search_hit])
    monkeypatch.setattr(case_research, "web_search", search)
    result = case_research.research_cases(site_data(), ["公共空间"], ["词一", "词二"])
    assert result["search_queries"] == ["词一", "词二"]
    assert [call.args[0] for call in search.call_args_list] == ["词一", "词二"]
    assert len(result["filtered_cases"]) == 1
    assert not any(task == "generate_search_queries" for task, _, _ in fake_llm.calls)
    case_research.research_cases(site_data(), ["公共空间"], [])
    assert search.call_count == 2


def test_dedup_and_filter_with_source_traceability(fake_llm, monkeypatch, search_hit):
    search = Mock(return_value=[search_hit, {**search_hit, "url": search_hit["url"] + "?utm_source=test#top"}])
    monkeypatch.setattr(case_research, "web_search", search)
    result = case_research.research_cases(site_data(), ["公共空间"])
    assert len(result["filtered_cases"]) == len(result["case_analysis"]) == 1
    case = Case.model_validate(result["filtered_cases"][0])
    analysis = CaseAnalysis.model_validate(result["case_analysis"][0])
    assert case.name == search_hit["title"] and case.source == search_hit["url"]
    assert search_hit["source"] in case.relevance
    assert analysis.case == case.name
    assert "专业推理" in analysis.applicable_reference[0]
    assert any("摘要" in item for item in analysis.limitations)


@pytest.mark.parametrize("failure", [False, True])
def test_no_results_or_tool_failures_never_fabricate_cases(fake_llm, monkeypatch, failure):
    search = Mock(side_effect=WebSearchError("失败")) if failure else Mock(return_value=[])
    monkeypatch.setattr(case_research, "web_search", search)
    result = case_research.research_cases(site_data(), ["公共空间"], ["词一", "词二"])
    assert result == {"search_queries": ["词一", "词二"], "filtered_cases": [], "case_analysis": []}
    assert search.call_count == 2
    assert not any(task == "analyze_cases" for task, _, _ in fake_llm.calls)


def test_partial_failure_keeps_successful_query(fake_llm, monkeypatch, search_hit):
    monkeypatch.setattr(case_research, "web_search", Mock(side_effect=[WebSearchError("失败"), [search_hit]]))
    result = case_research.research_cases(site_data(), ["公共空间"], ["词一", "词二"])
    assert len(result["filtered_cases"]) == 1


def test_case_filtering_is_llm_decision_not_keyword_rule(fake_llm, monkeypatch, search_hit):
    site = site_data()
    monkeypatch.setattr(case_research, "web_search", Mock(return_value=[search_hit]))
    def reject(prompt, schema, **kwargs):
        return schema(selected_cases=[])
    monkeypatch.setattr(case_research, "call_llm_structured", reject)
    result = case_research.research_cases(site, ["公共空间"], ["当前词"])
    assert result["filtered_cases"] == result["case_analysis"] == []


def test_case_research_rejects_invalid_complex_input():
    with pytest.raises(ValidationError):
        case_research.research_cases({"project_positioning": 42}, ["公共空间"])


@pytest.mark.parametrize("mismatch", ["source", "title", "analysis"])
def test_llm_cannot_invent_sources_or_unlinked_cases(fake_llm, monkeypatch, search_hit, mismatch):
    site = site_data()
    monkeypatch.setattr(case_research, "web_search", Mock(return_value=[search_hit]))
    def invented(selection, evidence):
        case = Case(name="新标题" if mismatch == "title" else search_hit["title"], location="未知", project_type="公共空间",
                    source="https://invented.invalid" if mismatch == "source" else search_hit["url"], relevance="推理")
        analysis = CaseAnalysis(case="无对应案例" if mismatch == "analysis" else case.name,
                                relevance_reason="推理", spatial_strategy=[], applicable_reference=[], limitations=[])
        return case_research._CaseResults(filtered_cases=[case], case_analysis=[analysis])
    monkeypatch.setattr(case_research, "_map_selected_cases", invented)
    with pytest.raises(LLMError):
        case_research.research_cases(site, ["公共空间"], ["词"])


@pytest.mark.parametrize("verdict", ["PASS", "FAIL 空间策略重复"])
def test_concept_quality_checks_once_and_regenerates_at_most_once(fake_llm, verdict):
    fake_llm.quality = [verdict]
    result = concept_generation.generate_concepts("项目资料", site_data())
    assert fake_llm.generation_count == (1 if verdict == "PASS" else 2)
    assert [task for task, _, _ in fake_llm.calls].count("quality_check") == 1
    assert set(result) == {"opportunities", "vision", "concepts", "images"}
    assert result["images"] == []
    Vision.model_validate(result["vision"])
    assert 2 <= len(result["concepts"]) <= 3
    for item in result["opportunities"]:
        DesignOpportunity.model_validate(item)
    for item in result["concepts"]:
        Concept.model_validate(item)
    for task, _, kwargs in fake_llm.calls:
        if task == "quality_check":
            assert kwargs["temperature"] == config.LLM_TEMPERATURE_DECISION
        elif task in {"opportunities_and_vision", "generate_concepts", "regenerate_concepts"}:
            assert kwargs["temperature"] == config.LLM_TEMPERATURE_GENERATION


def test_concept_respects_disabled_regeneration(fake_llm, monkeypatch):
    monkeypatch.setattr(config, "MAX_CONCEPT_REGENERATIONS", 0)
    fake_llm.quality = ["FAIL 依据不足"]
    result = concept_generation.generate_concepts("项目资料", site_data())
    assert fake_llm.generation_count == 1 and result["concepts"]


def test_invalid_quality_verdict_raises_without_state_output(fake_llm):
    fake_llm.quality = ["不确定"]
    with pytest.raises(LLMError):
        concept_generation.generate_concepts("项目资料", site_data())


def test_report_only_passes_existing_results_and_never_mutates(fake_llm, monkeypatch):
    site = site_data()
    result = concept_generation.generate_concepts("项目资料", site)
    inputs = ({"project_background": "用户原文"}, site, [], result["opportunities"],
              result["vision"], result["concepts"], result["images"])
    before = deepcopy(inputs)
    report = Mock(return_value="# 已有成果\n\n仅组织已有结论")
    monkeypatch.setattr(report_composition, "call_llm", report)
    assert report_composition.compose_report(*inputs) == "# 已有成果\n\n仅组织已有结论"
    assert inputs == before
    prompt = report.call_args.args[0]
    assert "用户原文" in prompt and result["concepts"][0]["name"] in prompt
    assert "不得新建场地判断" in prompt
    assert report.call_args.kwargs["temperature"] == config.LLM_TEMPERATURE_ANALYSIS


def test_source_fact_limits_are_present_in_case_prompt(fake_llm, monkeypatch, search_hit):
    site = site_data()
    original = case_research.call_llm_structured
    capture = Mock(wraps=original)
    monkeypatch.setattr(case_research, "call_llm_structured", capture)
    monkeypatch.setattr(case_research, "web_search", Mock(return_value=[search_hit]))
    case_research.research_cases(site, ["公共空间"], ["词"])
    prompt = capture.call_args.args[0]
    assert "不得补造项目规模、面积、建成年份、设计单位" in prompt
    assert "不将推理伪装成网页事实" in prompt


@pytest.mark.parametrize("variant,valid", [
    ("full_url", True),
    ("bare_domain", False),
    ("www_domain", False),
    ("website_label", False),
    ("official_label", False),
    ("rewritten_title", False),
    ("truncated_title", False),
    ("removed_subtitle", False),
    ("cross_source", False),
    ("exact_metadata", True),
])
def test_case_source_contract_keeps_exact_guard(monkeypatch, variant, valid):
    import json
    from conftest import make_site
    # Formal business objects construct the mock candidates; only provenance is varied.
    original = Case(name="Example Urban Renewal Project", location="未提供", project_type="城市更新",
                    source="https://example.com/projects/urban-renewal", relevance="专业推理：更新策略参考")
    other = Case(name="Shanghai Urban Renewal Project (Phase I)", location="未提供", project_type="城市更新",
                 source="https://other.example/projects/shanghai?phase=1", relevance="专业推理：更新策略参考")
    evidence = [{"title": case.name, "url": case.source, "snippet": "Urban renewal project overview",
                 "source": domain} for case, domain in ((original, "example.com"), (other, "other.example"))]
    candidate_data = (other if variant in {"rewritten_title", "exact_metadata"} else original).model_dump()
    if variant in {"bare_domain", "www_domain", "website_label", "official_label"}:
        candidate_data["source"] = {"bare_domain": "example.com", "www_domain": "www.example.com",
                                    "website_label": "官网", "official_label": "官方网站"}[variant]
    elif variant == "rewritten_title":
        candidate_data["name"] = "Shanghai Urban Renewal Project"
    elif variant == "truncated_title":
        candidate_data["name"] = "Example Urban Renewal"
    elif variant == "removed_subtitle":
        original = original.model_copy(update={"name": "Example Urban Renewal Project: Waterfront Connections"})
        evidence[0]["title"] = original.name
    elif variant == "cross_source":
        candidate_data["source"] = other.source  # Both values exist, but belong to different evidence.
    candidate = Case.model_validate(candidate_data)
    analysis = CaseAnalysis(case=candidate.name, relevance_reason="专业推理：更新策略参考",
                            spatial_strategy=["开放空间连接"], applicable_reference=["专业推理：改善步行联系"],
                            limitations=["仅有摘要证据"])
    search = Mock(return_value=evidence)
    monkeypatch.setattr(case_research, "web_search", search)
    def structured_response(prompt, schema, **kwargs):
        assert "当前任务：analyze_cases\n" in prompt
        current = json.loads(prompt.rsplit("INPUT_JSON:\n", 1)[1])["search_results"]
        assert current == [{**item, "source_id": f"src_{i:03d}"} for i, item in enumerate(evidence, 1)]
        assert "标题和完整 URL 由程序根据 source_id" in prompt
        assert "不能组合多个 evidence 的来源" in prompt
        from src.skills.case_research import _SelectedCase
        return schema(selected_cases=[_SelectedCase(source_id="src_001", location="未提供", project_type="城市更新",
            relevance="推理", relevance_reason="推理", spatial_strategy=[], applicable_reference=[], limitations=[])])
    llm = Mock(side_effect=structured_response)
    monkeypatch.setattr(case_research, "call_llm_structured", llm)
    # Fault injection after mapping verifies the original exact guard, not model metadata generation.
    monkeypatch.setattr(case_research, "_map_selected_cases", lambda *a: case_research._CaseResults(
        filtered_cases=[candidate], case_analysis=[analysis]))
    if valid:
        result = case_research.research_cases(make_site().model_dump(), ["更新策略"], ["更新案例"])
        assert result["filtered_cases"] == [candidate.model_dump()]
        assert result["case_analysis"] == [analysis.model_dump()]
    else:
        # Pydantic accepts the str; the existing exact provenance guard still rejects it.
        with pytest.raises(LLMError, match="^案例来源或标题不属于检索证据$"):
            case_research.research_cases(make_site().model_dump(), ["更新策略"], ["更新案例"])
    assert llm.call_count == search.call_count == 1


@pytest.mark.parametrize("references,enabled,capable,expected", [(None, True, True, "text2img"),
    (["site.png"], False, True, "text2img"), (["site.png"], True, False, "text2img"),
    (["site.png"], True, True, "img2img")])
def test_image_mode_and_contract(fake_llm, fake_image, monkeypatch, references, enabled, capable, expected):
    monkeypatch.setattr(config, "USE_IMG2IMG", enabled)
    monkeypatch.setattr(config, "image_reference_limit", lambda: 3 if capable else 0)
    result = concept_generation.generate_concepts("项目资料", site_data(), site_images=references)
    assert len(result["images"]) == len(result["concepts"]) == fake_image.call_count == 2
    for image, concept in zip(result["images"], result["concepts"]):
        parsed = GeneratedImage.model_validate(image)
        assert parsed.mode == expected and parsed.concept_name == concept["name"]
        assert parsed.reference_images == (references if expected == "img2img" else [])
        assert concept["name"] in parsed.prompt and result["vision"]["theme"] in parsed.prompt
        assert concept["spatial_strategy"] in parsed.prompt
    assert all(task != "image_reference_check" for task, _, _ in fake_llm.calls) == (expected == "text2img")


def test_only_final_concepts_receive_images(fake_llm, fake_image):
    fake_llm.quality = ["FAIL 策略重复"]
    def after_quality(*args, **kwargs):
        assert fake_llm.generation_count == 2
        assert [task for task, _, _ in fake_llm.calls].count("quality_check") == 1
        image = GeneratedImage(concept_name="示例", image_url="https://example.com/image.png", prompt=args[0],
                               mode="text2img", reference_images=[])
        return {"image_url": image.image_url, "mode": image.mode}
    fake_image.side_effect = after_quality
    result = concept_generation.generate_concepts("项目资料", site_data())
    tasks = [task for task, _, _ in fake_llm.calls]
    assert tasks.index("regenerate_concepts") < tasks.index("image_prompt")
    assert fake_image.call_count == len(result["concepts"]) == 2
    assert "quality_check" not in result


@pytest.mark.parametrize("all_failed", [False, True])
def test_image_failure_preserves_concepts_and_report(fake_llm, fake_image, all_failed):
    success = GeneratedImage(concept_name="示例", image_url="https://example.com/success.png", prompt="示例",
                             mode="text2img", reference_images=[])
    fake_image.side_effect = [ImageGenerationError("失败"), ImageGenerationError("失败") if all_failed else
                             {"image_url": success.image_url, "mode": success.mode}]
    site = site_data()
    result = concept_generation.generate_concepts("项目资料", site)
    assert len(result["images"]) == (0 if all_failed else 1)
    assert len(result["concepts"]) == 2 and fake_image.call_count == 2
    assert report_composition.compose_report({}, site, [], result["opportunities"], result["vision"],
                                              result["concepts"], result["images"])
    report_inputs = fake_llm.calls[-1][1]
    assert report_inputs["images"] == result["images"]


@pytest.mark.parametrize("verdict", ["FAIL", "error"])
def test_unusable_reference_falls_back_in_skill(fake_llm, fake_image, monkeypatch, verdict):
    monkeypatch.setattr(config, "USE_IMG2IMG", True)
    original = concept_generation.call_llm
    def text(prompt, **kwargs):
        if "当前任务：image_reference_check\n" in prompt:
            if verdict == "error":
                raise LLMError("参考图不可读或模型不支持")
            return "FAIL"
        return original(prompt, **kwargs)
    monkeypatch.setattr(concept_generation, "call_llm", text)
    result = concept_generation.generate_concepts("项目资料", site_data(), site_images=["site.png"])
    assert all(image["mode"] == "text2img" for image in result["images"])
    assert all(call.kwargs["reference_images"] is None for call in fake_image.call_args_list)


def test_reference_selection_respects_provider_limit(fake_llm, fake_image, monkeypatch):
    monkeypatch.setattr(config, "USE_IMG2IMG", True)
    refs = [f"site{i}.png" for i in range(5)]
    result = concept_generation.generate_concepts("项目资料", site_data(), site_images=refs)
    assert all(image["reference_images"] == refs[:3] for image in result["images"])
    check = next(kwargs for task, _, kwargs in fake_llm.calls if task == "image_reference_check")
    assert check["images"] == refs[:3]


@pytest.mark.parametrize("source_id", ["", "src_999", "src_000", "other_run_src_001"])
def test_source_id_unknown_rejected(fake_llm, monkeypatch, search_hit, source_id):
    site = site_data()
    monkeypatch.setattr(case_research, "web_search", lambda query: [search_hit])
    selected = case_research._SelectedCase(source_id=source_id, location="未知", project_type="更新",
        relevance="推理", relevance_reason="推理", spatial_strategy=[], applicable_reference=[], limitations=[])
    monkeypatch.setattr(case_research, "call_llm_structured", lambda *a, **k:
        case_research._CaseSelection(selected_cases=[selected]))
    with pytest.raises(LLMError, match="案例 source_id 不属于当前检索证据"):
        case_research.research_cases(site, ["更新"], ["当前查询"])


def test_source_id_mapping_preserves_exact_metadata_and_pairing(fake_llm, monkeypatch, search_hit):
    second = {**search_hit, "title": "Shanghai&rsquo;s Waterfront (Phase I) [PDF]",
              "url": "https://example.com/full/path.pdf?phase=1#page=2"}
    monkeypatch.setattr(case_research, "web_search", lambda query: [search_hit, second])
    result = case_research.research_cases(site_data(), ["更新"], ["当前查询"])
    assert [(item["name"], item["source"]) for item in result["filtered_cases"]] == [
        (item["title"], item["url"]) for item in (search_hit, second)]
    assert [item["case"] for item in result["case_analysis"]] == [search_hit["title"], second["title"]]
    assert "source_id" not in str(result)
    fields = case_research._SelectedCase.model_fields
    assert not {"name", "source", "title", "url", "case"} & fields.keys()
    selected = case_research._SelectedCase(source_id="src_001", location="未知", project_type="更新",
        relevance="推理", relevance_reason="推理", spatial_strategy=[], applicable_reference=[], limitations=[])
    for forbidden in ("name", "source", "title", "url", "case"):
        with pytest.raises(ValidationError):
            case_research._SelectedCase.model_validate({**selected.model_dump(), forbidden: "rewritten"})


def test_duplicate_source_id_keeps_existing_duplicate_guard(fake_llm, monkeypatch, search_hit):
    site = site_data()
    monkeypatch.setattr(case_research, "web_search", lambda query: [search_hit])
    selected = case_research._SelectedCase(source_id="src_001", location="未知", project_type="更新",
        relevance="推理", relevance_reason="推理", spatial_strategy=[], applicable_reference=[], limitations=[])
    monkeypatch.setattr(case_research, "call_llm_structured", lambda *a, **k:
        case_research._CaseSelection(selected_cases=[selected, selected]))
    with pytest.raises(LLMError, match="^案例标识重复，无法可靠对应分析$"):
        case_research.research_cases(site, ["更新"], ["当前查询"])
