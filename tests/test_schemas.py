from copy import deepcopy

import pytest
from pydantic import ValidationError

from src.schemas.case import Case, CaseAnalysis
from src.schemas.concept import Concept, DesignOpportunity, GeneratedImage, Vision
from src.schemas.site_info import SWOT, SiteAnalysis


SWOT_DATA = {
    "strengths": ["滨水资源"],
    "weaknesses": ["慢行联系不足"],
    "opportunities": ["公共空间建设需求"],
    "threats": ["洪水风险"],
}
SITE_DATA = {
    "project_positioning": "滨水公共空间",
    "location_conditions": {"city": "示例城市"},
    "functional_conditions": {},
    "landscape_resources": {"waterfront": "南侧河流"},
    "public_space": {},
    "transportation": {},
    "spatial_conditions": {},
    "swot": SWOT_DATA,
    "analysis_summary": "改善城市与滨水空间联系",
}
VISION_DATA = {
    "theme": "滨水城市客厅",
    "positioning": "公共活动节点",
    "core_goal": "提升公共空间连续性",
    "spatial_idea": "以慢行系统串联滨水节点",
}
MODEL_CASES = [
    (SWOT, SWOT_DATA),
    (SiteAnalysis, SITE_DATA),
    (Case, {
        "name": "示例案例", "location": "示例城市", "project_type": "滨水更新",
        "source": "https://example.com/project", "relevance": "公共空间组织参考",
    }),
    (CaseAnalysis, {
        "case": "示例案例", "relevance_reason": "具有类似空间问题",
        "spatial_strategy": ["连续慢行"], "applicable_reference": ["滨水节点联系"],
        "limitations": ["场地尺度不同"],
    }),
    (DesignOpportunity, {
        "opportunity": "连接城市与滨水空间", "basis": "场地分析", "priority": "high",
    }),
    (Vision, VISION_DATA),
    (Concept, {
        "name": "滨水公共客厅", "core_concept": "公共活动与滨水资源融合",
        "design_opportunities": ["强化滨水联系"], "spatial_strategy": "串联公共节点",
        "key_actions": ["补充慢行联系"], "case_references": [],
    }),
    (GeneratedImage, {
        "concept_name": "滨水公共客厅", "image_url": "concept.png", "prompt": "滨水空间",
        "mode": "text2img", "reference_images": [],
    }),
]
MODEL_IDS = [model.__name__ for model, _ in MODEL_CASES]


@pytest.mark.parametrize("model,data", MODEL_CASES, ids=MODEL_IDS)
def test_valid_structure_round_trips(model, data):
    assert model.model_validate(data).model_dump() == data


@pytest.mark.parametrize("model,data", MODEL_CASES, ids=MODEL_IDS)
def test_missing_required_field_fails(model, data):
    invalid = deepcopy(data)
    del invalid[next(iter(invalid))]
    with pytest.raises(ValidationError):
        model.model_validate(invalid)


@pytest.mark.parametrize("model,data", MODEL_CASES, ids=MODEL_IDS)
def test_wrong_field_type_fails(model, data):
    invalid = deepcopy(data)
    invalid[next(iter(invalid))] = 42
    with pytest.raises(ValidationError):
        model.model_validate(invalid)


def test_vision_requires_the_unified_object():
    assert set(Vision.model_fields) == {"theme", "positioning", "core_goal", "spatial_idea"}
    with pytest.raises(ValidationError):
        Vision.model_validate("滨水城市客厅")


def test_swot_is_a_nested_validated_object():
    site = SiteAnalysis.model_validate(SITE_DATA)
    assert isinstance(site.swot, SWOT)
    invalid = deepcopy(SITE_DATA)
    invalid["swot"]["strengths"] = "滨水资源"
    with pytest.raises(ValidationError):
        SiteAnalysis.model_validate(invalid)


@pytest.mark.parametrize("field", [
    "site_strengths", "site_weaknesses", "site_opportunities", "site_threats",
])
def test_deprecated_flat_swot_fields_are_rejected(field):
    invalid = deepcopy(SITE_DATA)
    invalid[field] = ["旧结构"]
    assert field not in SiteAnalysis.model_fields
    with pytest.raises(ValidationError):
        SiteAnalysis.model_validate(invalid)


def test_flat_swot_cannot_replace_the_nested_object():
    invalid = deepcopy(SITE_DATA)
    del invalid["swot"]
    invalid.update({f"site_{key}": value for key, value in SWOT_DATA.items()})
    with pytest.raises(ValidationError):
        SiteAnalysis.model_validate(invalid)


def test_unsupported_image_mode_fails():
    invalid = deepcopy(MODEL_CASES[-1][1])
    invalid["mode"] = "unknown"
    with pytest.raises(ValidationError):
        GeneratedImage.model_validate(invalid)
