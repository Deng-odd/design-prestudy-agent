from copy import deepcopy
from importlib import import_module
from unittest.mock import Mock

import pytest
import requests
from tavily.errors import BadRequestError, ForbiddenError, InvalidAPIKeyError, UsageLimitExceededError
from tavily.errors import TimeoutError as TavilyTimeoutError

from src import config
from src.agent.state import create_initial_state
from src.tools import web_search
from src.tools.web_search import WebSearchError

tool = import_module("src.tools.web_search")


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError("Provider error", response=response)


def test_mapping_and_provider_metadata_is_removed(sdk_search):
    sdk_search.return_value = {"results": [{"title": "项目", "url": "https://WWW.Example.com:443/project",
                                          "content": "摘要", "source": "不可信来源", "score": .9}],
                               "request_id": "metadata"}
    assert web_search("公共空间", 3) == [{"title": "项目", "url": "https://WWW.Example.com:443/project",
                                        "snippet": "摘要", "source": "www.example.com"}]
    sdk_search.assert_called_once_with(query="公共空间", max_results=3, timeout=30)


def test_empty_and_safe_missing_fields(sdk_search):
    assert web_search("query") == []
    sdk_search.return_value = {"results": [{"url": "https://example.com/project", "title": None, "content": 3},
                                          {}, {"url": "invalid"}, {"url": "file:///local"},
                                          {"url": "https://user:password@example.com/"},
                                          {"url": "https://example.com:bad/"}]}
    assert web_search("query") == [{"title": "", "url": "https://example.com/project",
                                   "snippet": "", "source": "example.com"}]


@pytest.mark.parametrize("error", [requests.Timeout(), requests.ConnectionError(), TavilyTimeoutError(30),
                                  UsageLimitExceededError("rate limit"), http_error(408), http_error(429),
                                  http_error(500), http_error(503)])
def test_retryable_errors_eventually_succeed(sdk_search, error):
    sdk_search.side_effect = [error, {"results": []}]
    assert web_search("query") == []
    assert sdk_search.call_count == 2
    tool.sleep.assert_called_once_with(1)


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_retry_limit_is_additional_attempts(sdk_search, monkeypatch, retries):
    monkeypatch.setattr(config, "TOOL_MAX_RETRIES", retries)
    sdk_search.side_effect = requests.Timeout()
    with pytest.raises(WebSearchError):
        web_search("query")
    assert sdk_search.call_count == retries + 1
    assert tool.sleep.call_count == retries


@pytest.mark.parametrize("error", [InvalidAPIKeyError("secret must not escape"), BadRequestError("invalid"),
                                  ForbiddenError("forbidden"), http_error(401), http_error(403),
                                  http_error(400), ValueError("invalid response")])
def test_permanent_errors_do_not_retry_or_leak(sdk_search, error):
    sdk_search.side_effect = error
    with pytest.raises(WebSearchError) as caught:
        web_search("query")
    assert "secret" not in str(caught.value)
    assert sdk_search.call_count == 1
    tool.sleep.assert_not_called()


@pytest.mark.parametrize("query,limit", [("", 10), (None, 10), ("query", 0), ("query", 21), ("query", True)])
def test_invalid_input_never_calls_provider(sdk_search, query, limit):
    with pytest.raises(WebSearchError):
        web_search(query, limit)
    sdk_search.assert_not_called()


def test_missing_key_and_unsupported_provider_never_calls(sdk_search, monkeypatch):
    monkeypatch.setattr(config, "TAVILY_API_KEY", "")
    with pytest.raises(WebSearchError):
        web_search("query")
    monkeypatch.setattr(config, "TAVILY_API_KEY", "test-only-placeholder")
    monkeypatch.setattr(config, "WEB_SEARCH_PROVIDER", "unsupported")
    with pytest.raises(WebSearchError):
        web_search("query")
    sdk_search.assert_not_called()


def test_tool_does_not_accept_or_modify_state(sdk_search):
    state = create_initial_state("query")
    before = deepcopy(state)
    assert web_search(state["user_input"]) == []
    assert state == before
    with pytest.raises(WebSearchError):
        web_search(state)


@pytest.mark.parametrize("response", [{}, {"results": None}, [], {"results": {}}])
def test_invalid_response_is_not_empty_success_or_retried(sdk_search, response):
    sdk_search.return_value = response
    with pytest.raises(WebSearchError):
        web_search("query")
    assert sdk_search.call_count == 1


def test_installed_sdk_request_and_tool_mapping_offline(monkeypatch):
    monkeypatch.setattr(config, "TAVILY_API_KEY", "test-only-placeholder")
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"results":[{"title":"Park","url":"https://example.com/park","content":"Public space"}]}'
    post = Mock(return_value=response)
    monkeypatch.setattr(requests.Session, "post", post)
    assert web_search("park", 1)[0]["snippet"] == "Public space"
    assert post.call_count == 1


def test_tool_retries_are_independent_of_llm_budget(sdk_search, monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 0)
    monkeypatch.setattr(config, "TOOL_MAX_RETRIES", 1)
    sdk_search.side_effect = [requests.Timeout(), {"results": []}]
    assert web_search("query") == []
    assert sdk_search.call_count == 2
