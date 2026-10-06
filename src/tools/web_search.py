"""搜索能力的技术边界：标准化结果和有限重试，不接收 Agent State。"""

from time import sleep
from urllib.parse import urlsplit

from requests.exceptions import ConnectionError, HTTPError, Timeout
from tavily import TavilyClient
from tavily.errors import TimeoutError as TavilyTimeoutError
from tavily.errors import UsageLimitExceededError

from src import config


class WebSearchError(RuntimeError):
    """搜索最终不可用；不向上层暴露请求、凭据或 Provider 原始响应。"""


def _retryable(error: Exception) -> bool:
    if isinstance(error, (Timeout, ConnectionError, TavilyTimeoutError, UsageLimitExceededError)):
        return True
    if isinstance(error, HTTPError) and error.response is not None:
        return error.response.status_code in {408, 429} or 500 <= error.response.status_code < 600
    return False


def _normalize(response: dict) -> list[dict]:
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        raise WebSearchError("搜索响应结构无效")
    results = []
    for item in response["results"]:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        url = item["url"].strip()
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
                continue
            parsed.port
        except ValueError:
            continue
        results.append({
            "title": item["title"].strip() if isinstance(item.get("title"), str) else "",
            "url": url,
            "snippet": item["content"].strip() if isinstance(item.get("content"), str) else "",
            "source": hostname,
        })
    return results


def web_search(query: str, max_results: int | None = None) -> list[dict]:
    """返回 title/url/snippet/source；最多初次调用 + TOOL_MAX_RETRIES 次重试。"""
    if not isinstance(query, str) or not query.strip():
        raise WebSearchError("搜索 query 必须为非空字符串")
    limit = config.WEB_SEARCH_MAX_RESULTS if max_results is None else max_results
    if type(limit) is not int or not 1 <= limit <= 20:
        raise WebSearchError("搜索结果数量必须为 1 到 20 的整数")
    if config.WEB_SEARCH_PROVIDER != "tavily":
        raise WebSearchError("当前搜索 Provider 不受支持")
    if not config.TAVILY_API_KEY.strip():
        raise WebSearchError("搜索凭据未配置")
    try:
        with TavilyClient(api_key=config.TAVILY_API_KEY) as client:
            for attempt in range(config.TOOL_MAX_RETRIES + 1):
                try:
                    response = client.search(query=query.strip(), max_results=limit, timeout=30)
                    return _normalize(response)[:limit]
                except Exception as error:
                    if not _retryable(error) or attempt >= config.TOOL_MAX_RETRIES:
                        raise WebSearchError("搜索请求最终失败") from None
                    sleep(min(2 ** attempt, 4))
    except WebSearchError:
        raise
    except Exception:
        raise WebSearchError("搜索客户端不可用") from None
