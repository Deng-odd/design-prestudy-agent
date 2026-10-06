"""单一 StateGraph，固定九个 Node，无持久化或暂停恢复机制。"""

from langgraph.graph import END, START, StateGraph

from src.agent import nodes
from src.agent.routes import route_case_need, route_info, route_research
from src.agent.state import AgentState


def build_graph():
    builder = StateGraph(AgentState)
    for name in (
        "parse_and_check", "ask_user", "site_analysis", "check_case_need", "case_research",
        "check_research", "refine_search", "concept_generation", "report_composition",
    ):
        builder.add_node(name, getattr(nodes, name))
    builder.add_edge(START, "parse_and_check")
    builder.add_conditional_edges("parse_and_check", route_info, {
        "ask_user": "ask_user", "site_analysis": "site_analysis",
    })
    builder.add_edge("ask_user", END)
    builder.add_edge("site_analysis", "check_case_need")
    builder.add_conditional_edges("check_case_need", route_case_need, {
        "case_research": "case_research", "concept_generation": "concept_generation",
    })
    builder.add_edge("case_research", "check_research")
    builder.add_conditional_edges("check_research", route_research, {
        "refine_search": "refine_search", "concept_generation": "concept_generation",
    })
    builder.add_edge("refine_search", "case_research")
    builder.add_edge("concept_generation", "report_composition")
    builder.add_edge("report_composition", END)
    return builder.compile()


graph = build_graph()
