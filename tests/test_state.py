from typing import get_type_hints

from src.agent.state import AgentState, create_initial_state


def test_initial_state_contains_only_input_and_search_counter():
    state = create_initial_state("滨水公共空间，北侧临城市道路", ["site.png"])

    assert state == {
        "user_input": "滨水公共空间，北侧临城市道路",
        "site_images": ["site.png"],
        "search_attempts": 0,
    }


def test_missing_site_images_is_an_independent_empty_list():
    first = create_initial_state("项目一")
    second = create_initial_state("项目二")
    first["site_images"].append("site.png")

    assert second["site_images"] == []
    assert second["search_attempts"] == 0
    assert set(second) == {"user_input", "site_images", "search_attempts"}


def test_initial_state_does_not_share_the_supplied_image_list():
    images = ["site.png"]
    state = create_initial_state("项目", images)
    images.append("later.png")

    assert state["site_images"] == ["site.png"]


def test_state_keeps_nullable_requirements_and_excludes_internal_fields():
    fields = get_type_hints(AgentState)

    assert fields["client_requirements"] == str | None
    assert fields["missing_critical"] == list[str]
    assert fields["missing_optional"] == list[str]
    assert AgentState.__required_keys__ == frozenset()
    assert not {
        "missing_information", "quality_check", "current_node", "next_action",
        "agent_status", "tool_results", "USE_IMG2IMG", "REFERENCE_STRENGTH",
    } & fields.keys()
