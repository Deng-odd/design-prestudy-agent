"""九个 Node：只做输入判断、Skill 调度和 partial State updates。"""

from pydantic import BaseModel, ConfigDict, model_validator

from src import config
from src.llm import call_llm_structured, load_prompt
from src.agent.state import AgentState
from src.schemas import Case, CaseAnalysis, Concept, DesignOpportunity, GeneratedImage, SiteAnalysis, Vision
from src.skills.case_research import research_cases
from src.skills.concept_generation import generate_concepts
from src.skills.report_composition import compose_report
from src.skills.site_analysis import analyze_site


class _ParsedInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_background: str
    location: str
    planning_conditions: dict
    client_requirements: str | None
    site_image_description: str
    info_sufficient: bool
    missing_critical: list[str]
    missing_optional: list[str]
    followup_question: str

    @model_validator(mode="after")
    def consistent_check(self):
        if self.info_sufficient != (not self.missing_critical):
            raise ValueError("信息充分性与关键缺失不一致")
        if not self.info_sufficient and not self.followup_question.strip():
            raise ValueError("信息不足时必须追问")
        return self


class _CaseNeed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    need_case_research: bool
    research_direction: list[str]


class _ResearchCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    research_sufficient: bool
    research_gaps: list[str]


class _SearchQueries(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    search_queries: list[str]


def parse_and_check(state: AgentState) -> dict:
    prompt = load_prompt("parse_input.md", "parse_and_check", {"user_input": state["user_input"]})
    return call_llm_structured(prompt, _ParsedInput, images=state.get("site_images"),
                               temperature=config.LLM_TEMPERATURE_DECISION).model_dump()


def ask_user(state: AgentState) -> dict:
    # 追问已经由 parse_and_check 写入，调用方从最终 State 读取；本节点不改 State。
    return {}


def site_analysis(state: AgentState) -> dict:
    result = analyze_site(
        state["project_background"], state["location"], state.get("planning_conditions"),
        state.get("client_requirements"), state.get("site_image_description"), state.get("site_images"),
    )
    return {"site_analysis": SiteAnalysis.model_validate(result["site_analysis"]).model_dump()}


def check_case_need(state: AgentState) -> dict:
    site = SiteAnalysis.model_validate(state["site_analysis"])
    inputs = {"site_analysis": site.model_dump(), "project_background": state.get("project_background"),
              "client_requirements": state.get("client_requirements")}
    return call_llm_structured(load_prompt("parse_input.md", "check_case_need", inputs), _CaseNeed,
                               temperature=config.LLM_TEMPERATURE_DECISION).model_dump()


def case_research(state: AgentState) -> dict:
    result = research_cases(state["site_analysis"], state["research_direction"], state.get("search_queries"))
    return {
        "search_queries": result["search_queries"],
        "filtered_cases": [Case.model_validate(item).model_dump() for item in result["filtered_cases"]],
        "case_analysis": [CaseAnalysis.model_validate(item).model_dump() for item in result["case_analysis"]],
        "search_attempts": state.get("search_attempts", 0) + 1,
    }


def check_research(state: AgentState) -> dict:
    cases = [Case.model_validate(item) for item in state.get("filtered_cases", [])]
    analyses = [CaseAnalysis.model_validate(item) for item in state.get("case_analysis", [])]
    inputs = {"filtered_cases": [case.model_dump() for case in cases],
              "case_analysis": [item.model_dump() for item in analyses],
              "research_direction": state.get("research_direction", []),
              "site_analysis": SiteAnalysis.model_validate(state["site_analysis"]).model_dump()}
    return call_llm_structured(load_prompt("research_cases.md", "check_research", inputs), _ResearchCheck,
                               temperature=config.LLM_TEMPERATURE_DECISION).model_dump()


def refine_search(state: AgentState) -> dict:
    inputs = {key: state.get(key, []) for key in (
        "research_gaps", "search_queries", "research_direction", "filtered_cases", "case_analysis",
    )}
    return call_llm_structured(load_prompt("research_cases.md", "refine_search", inputs), _SearchQueries,
                               temperature=config.LLM_TEMPERATURE_DECISION).model_dump()


def concept_generation(state: AgentState) -> dict:
    result = generate_concepts(
        state["project_background"], state["site_analysis"], state.get("client_requirements"),
        state.get("case_analysis"), state.get("site_images"),
    )
    return {
        "opportunities": [DesignOpportunity.model_validate(item).model_dump() for item in result["opportunities"]],
        "vision": Vision.model_validate(result["vision"]).model_dump(),
        "concepts": [Concept.model_validate(item).model_dump() for item in result["concepts"]],
        "images": [GeneratedImage.model_validate(item).model_dump() for item in result["images"]],
    }


def report_composition(state: AgentState) -> dict:
    context = {key: state.get(key) for key in (
        "project_background", "location", "planning_conditions", "client_requirements",
        "filtered_cases", "research_gaps", "need_case_research", "research_sufficient",
    )}
    context["filtered_cases"] = state.get("filtered_cases", [])
    context["research_gaps"] = state.get("research_gaps", [])
    report = compose_report(
        context, state["site_analysis"], state.get("case_analysis"), state["opportunities"],
        state["vision"], state["concepts"], state.get("images", []),
    )
    return {"final_report": report}
