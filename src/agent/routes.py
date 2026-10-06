"""只读取决策字段和业务计数，不执行专业任务。"""

from src import config
from src.agent.state import AgentState


def route_info(state: AgentState) -> str:
    return "site_analysis" if state["info_sufficient"] else "ask_user"


def route_case_need(state: AgentState) -> str:
    return "case_research" if state["need_case_research"] else "concept_generation"


def route_research(state: AgentState) -> str:
    if state["research_sufficient"] or state["search_attempts"] >= config.MAX_SEARCH_ATTEMPTS:
        return "concept_generation"
    return "refine_search"
