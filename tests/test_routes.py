import pytest

from src import config
from src.agent.routes import route_case_need, route_info, route_research


@pytest.mark.parametrize("sufficient,expected", [(False, "ask_user"), (True, "site_analysis")])
def test_route_info(sufficient, expected):
    assert route_info({"info_sufficient": sufficient}) == expected


@pytest.mark.parametrize("needed,expected", [(False, "concept_generation"), (True, "case_research")])
def test_route_case_need(needed, expected):
    assert route_case_need({"need_case_research": needed}) == expected


@pytest.mark.parametrize("sufficient,attempts,expected", [
    (True, 1, "concept_generation"), (False, 1, "refine_search"),
    (True, 2, "concept_generation"), (False, 2, "concept_generation"),
    (False, 3, "concept_generation"),
])
def test_route_research(sufficient, attempts, expected, monkeypatch):
    monkeypatch.setattr(config, "MAX_SEARCH_ATTEMPTS", 2)
    assert route_research({"research_sufficient": sufficient, "search_attempts": attempts}) == expected


def test_route_research_reads_configured_limit(monkeypatch):
    monkeypatch.setattr(config, "MAX_SEARCH_ATTEMPTS", 1)
    assert route_research({"research_sufficient": False, "search_attempts": 1}) == "concept_generation"
