"""
Tavily 搜索服务：封装关键词搜索，返回标准化结果列表。
"""

import concurrent.futures
import sys
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

_INTEL_DIR = Path(__file__).resolve().parent.parent
if str(_INTEL_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEL_DIR))

from config import get_config


_TAVILY_TIMEOUT_SECONDS = 30


def search_keyword(keyword: str, days_back: int = 1, max_results: int = 5) -> list[dict[str, Any]]:
    """搜索单个关键词，返回标准化结果列表。超过 30s 无响应则抛 TimeoutError。"""
    from tavily import TavilyClient
    cfg = get_config()
    client = TavilyClient(api_key=cfg.TAVILY_API_KEY)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            client.search,
            query=keyword, topic="news", days=days_back, max_results=max_results,
        )
        try:
            resp = future.result(timeout=_TAVILY_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Tavily 搜索超时（{_TAVILY_TIMEOUT_SECONDS}s）：{keyword}")
    return [_normalize(r, keyword) for r in resp.get("results", [])]


def search_keywords(keywords: list[str], days_back: int = 1) -> list[dict[str, Any]]:
    """批量搜索，返回所有结果的合并列表。失败的关键词打印错误后跳过。"""
    cfg = get_config()
    all_results = []
    for kw in keywords:
        try:
            results = search_keyword(kw, days_back=days_back, max_results=cfg.MAX_RESULTS_PER_KEYWORD)
            all_results.extend(results)
            print(f"  [{kw}] {len(results)} 条")
        except Exception as e:
            print(f"  [{kw}] 搜索失败: {e}")
    return all_results


def _normalize(r: dict[str, Any], keyword: str) -> dict[str, Any]:
    url = r.get("url", "").strip()
    return {
        "title": r.get("title", "").strip(),
        "url": url,
        "snippet": r.get("content", "").strip(),
        "source_name": (lambda n: n[4:] if n.startswith("www.") else n)(urlparse(url).netloc) if url else "",
        "pub_date": r.get("published_date", ""),
        "source_keyword": keyword,
        "source_channel": "tavily",
    }
