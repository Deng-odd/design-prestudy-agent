"""V1 顶层 State 与最小初始化，不包含系统配置或执行逻辑。"""

from typing import TypedDict


class AgentState(TypedDict, total=False):
    user_input: str
    site_images: list[str]

    project_background: str
    location: str
    planning_conditions: dict
    client_requirements: str | None
    site_image_description: str

    info_sufficient: bool
    missing_critical: list[str]
    missing_optional: list[str]
    followup_question: str

    site_analysis: dict

    need_case_research: bool
    research_direction: list[str]
    search_queries: list[str]
    filtered_cases: list[dict]
    case_analysis: list[dict]
    research_sufficient: bool
    research_gaps: list[str]
    search_attempts: int

    opportunities: list[dict]
    vision: dict
    concepts: list[dict]
    images: list[dict]

    final_report: str


def create_initial_state(
    user_input: str,
    site_images: list[str] | None = None,
) -> AgentState:
    """只初始化用户输入、图片列表和搜索轮次；复制图片列表避免共享修改。"""
    return {
        "user_input": user_input,
        "site_images": list(site_images) if site_images is not None else [],
        "search_attempts": 0,
    }
