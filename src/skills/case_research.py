"""搜索采集与 LLM 专业分析；技术检索保持独立 Tool 边界。"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict

from src import config
from src.llm import LLMError, call_llm_structured, load_prompt
from src.schemas import Case, CaseAnalysis, SiteAnalysis
from src.tools.web_search import WebSearchError, web_search


class _Queries(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    search_queries: list[str]


class _CaseResults(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    filtered_cases: list[Case]
    case_analysis: list[CaseAnalysis]


class _SelectedCase(BaseModel):
    """LLM selects provenance by ID; professional judgments remain model output."""
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str
    location: str
    project_type: str
    relevance: str
    relevance_reason: str
    spatial_strategy: list[str]
    applicable_reference: list[str]
    limitations: list[str]


class _CaseSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    selected_cases: list[_SelectedCase]


def _map_selected_cases(selection: _CaseSelection, evidence: list[dict]) -> _CaseResults:
    by_id = {item["source_id"]: item for item in evidence}
    cases, analyses = [], []
    for selected in selection.selected_cases:
        if selected.source_id not in by_id:
            raise LLMError("案例 source_id 不属于当前检索证据")
        source = by_id[selected.source_id]
        cases.append(Case(name=source["title"], source=source["url"], location=selected.location,
                          project_type=selected.project_type, relevance=selected.relevance))
        analyses.append(CaseAnalysis(case=source["title"], relevance_reason=selected.relevance_reason,
                                     spatial_strategy=selected.spatial_strategy,
                                     applicable_reference=selected.applicable_reference,
                                     limitations=selected.limitations))
    return _CaseResults(filtered_cases=cases, case_analysis=analyses)


def _url_identity(url: str) -> str:
    parsed = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"),
                       urlencode(sorted(query)), ""))


def research_cases(site_analysis: dict, research_direction: list[str],
                   search_queries: list[str] | None = None) -> dict:
    site = SiteAnalysis.model_validate(site_analysis)
    context = {"site_analysis": site.model_dump(), "research_direction": research_direction}
    if search_queries is None:
        queries = call_llm_structured(load_prompt("research_cases.md", "generate_search_queries", context),
                                      _Queries, temperature=config.LLM_TEMPERATURE_DECISION).search_queries
    else:
        queries = list(search_queries)
    merged = {}
    for query in queries:
        try:
            results = web_search(query)
        except WebSearchError:
            continue
        for result in results:
            identity = _url_identity(result["url"])
            previous = merged.get(identity)
            if previous is None or (bool(result["title"]), len(result["snippet"])) > (bool(previous["title"]), len(previous["snippet"])):
                merged[identity] = result
    if not merged:
        return {"search_queries": queries, "filtered_cases": [], "case_analysis": []}
    context["search_results"] = [{**item, "source_id": f"src_{index:03d}"}
                                 for index, item in enumerate(merged.values(), start=1)]
    selection = call_llm_structured(load_prompt("research_cases.md", "analyze_cases", context), _CaseSelection,
                                   temperature=config.LLM_TEMPERATURE_ANALYSIS)
    analyzed = _map_selected_cases(selection, context["search_results"])
    # Schema 负责类型；这里仅检查来源/关联完整性，不代替模型专业筛选。
    evidence = {item["url"]: item for item in merged.values()}
    names = {case.name for case in analyzed.filtered_cases}
    if len(names) != len(analyzed.filtered_cases):
        raise LLMError("案例标识重复，无法可靠对应分析")
    for case in analyzed.filtered_cases:
        if case.source not in evidence or case.name != evidence[case.source]["title"]:
            raise LLMError("案例来源或标题不属于检索证据")
    if any(item.case not in names for item in analyzed.case_analysis):
        raise LLMError("案例分析与已筛选案例无法对应")
    return {"search_queries": queries, **analyzed.model_dump()}
