"""基于已有成果生成 Markdown，不修改或新增专业结论。"""

from src import config
from src.llm import call_llm, load_prompt
from src.schemas import Case, CaseAnalysis, Concept, DesignOpportunity, GeneratedImage, SiteAnalysis, Vision


def compose_report(project_context: dict, site_analysis: dict, case_analysis: list[dict] | None,
                   opportunities: list[dict], vision: dict, concepts: list[dict], images: list[dict]) -> str:
    context = {key: project_context.get(key) for key in (
        "project_background", "location", "planning_conditions", "client_requirements",
        "research_gaps", "need_case_research", "research_sufficient",
    )}
    context["filtered_cases"] = [Case.model_validate(item).model_dump()
                                 for item in project_context.get("filtered_cases", [])]
    inputs = {"project_context": context,
              "site_analysis": SiteAnalysis.model_validate(site_analysis).model_dump(),
              "case_analysis": [CaseAnalysis.model_validate(item).model_dump() for item in case_analysis or []],
              "opportunities": [DesignOpportunity.model_validate(item).model_dump() for item in opportunities],
              "vision": Vision.model_validate(vision).model_dump(),
              "concepts": [Concept.model_validate(item).model_dump() for item in concepts],
              "images": [GeneratedImage.model_validate(item).model_dump() for item in images]}
    return call_llm(load_prompt("compose_report.md", "compose_report", inputs),
                    temperature=config.LLM_TEMPERATURE_ANALYSIS)
