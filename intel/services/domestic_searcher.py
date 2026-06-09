"""
CIOSH 情报雷达 · 国内搜索通道
百度新闻 / 知乎 / B站 三通道，统一返回与 searcher.py 相同的 dict schema。
任何通道失败均打印错误后返回 []，不向上抛出异常。
"""

import asyncio
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse

_INTEL_DIR = Path(__file__).resolve().parent.parent
if str(_INTEL_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEL_DIR))

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 百度时间范围参数（tbs）映射
_BAIDU_TBS = {1: "qdr:d", 7: "qdr:w", 30: "qdr:m", 90: "qdr:y"}


def _parse_baidu_date(text: str) -> str:
    """
    将百度搜索结果中的时间文本转为 ISO 日期字符串（YYYY-MM-DD）。
    支持："3天前" / "2小时前" / "昨天" / "2024年4月15日" / "2024-04-15" / "04-15"。
    无法识别时返回空字符串。
    """
    text = text.strip()
    if not text:
        return ""
    now = datetime.now()
    # 相对时间：N分钟前 / N小时前
    m = re.search(r"(\d+)\s*分钟前", text)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s*小时前", text)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).strftime("%Y-%m-%d")
    # 相对时间：N天前
    m = re.search(r"(\d+)\s*天前", text)
    if m:
        return (now - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
    if "昨天" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    # 绝对日期：YYYY年M月D日 或 YYYY年M月
    m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(20\d{2})年(\d{1,2})月", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    # 绝对日期：YYYY-MM-DD 或 MM-DD（当年）
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"^(\d{2})-(\d{2})$", text)
    if m:
        return f"{now.year}-{m.group(1)}-{m.group(2)}"
    return ""


# ─── 百度新闻 ──────────────────────────────────────────────────────────────────

def search_baidu(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]:
    """抓取百度新闻搜索结果，source_channel='baidu'。"""
    try:
        import requests
        from bs4 import BeautifulSoup

        tbs = _BAIDU_TBS.get(date_range_days, "qdr:d")
        url = f"https://www.baidu.com/s?tn=news&rn=20&word={quote(word)}&tbs={tbs}"
        headers = {
            "User-Agent": _UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.baidu.com/",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        # 百度新闻结果：h3/h4 内的 <a> 为标题链接
        for tag in soup.find_all(["h3", "h4"])[:max_results * 3]:
            a = tag.find("a", href=True)
            if not a:
                continue
            href = a.get("href", "")
            if not href.startswith("http"):
                continue
            title = a.get_text(strip=True)
            if not title:
                continue

            # 来源：同级或父级 span.c-author / span.c-gap-right
            parent = tag.parent or tag
            source_span = parent.find("span", class_=re.compile(r"c-author|c-gap-right|source"))
            source_name = source_span.get_text(strip=True) if source_span else urlparse(href).netloc

            # 摘要：c-line-clamp2 或相邻 p/div
            snippet_tag = parent.find(class_=re.compile(r"c-line-clamp|abstract|c-span"))
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

            # 发布日期：从结果区块提取时间戳（百度新闻常见 c-color-gray2 / c-gap-top-small）
            pub_date = ""
            date_span = parent.find("span", class_=re.compile(r"c-color-gray|c-gap-top|time|date"))
            if date_span:
                pub_date = _parse_baidu_date(date_span.get_text(strip=True))

            results.append({
                "title": title,
                "url": href,
                "snippet": snippet[:300],
                "source_name": source_name[:50],
                "pub_date": pub_date,
                "source_keyword": word,
                "source_channel": "baidu",
            })
            if len(results) >= max_results:
                break

        if not results:
            print(f"  [baidu] {word}: 0条 (HTTP {resp.status_code}, {len(resp.text)}B)")
        return results
    except Exception as e:
        print(f"  [baidu] {word}: 搜索失败 — {e}")
        return []


# ─── 知乎 ─────────────────────────────────────────────────────────────────────

def search_zhihu(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]:
    """解析知乎搜索 __NEXT_DATA__ JSON，source_channel='zhihu'。"""
    try:
        import json
        import requests
        from bs4 import BeautifulSoup

        url = f"https://www.zhihu.com/search?type=content&q={quote(word)}"
        headers = {
            "User-Agent": _UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.zhihu.com/",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            return []

        data = json.loads(script.string)
        # 知乎搜索结果路径
        search_result = (
            data.get("props", {})
                .get("pageProps", {})
                .get("searchResult", {})
                .get("data", [])
        )

        cutoff = datetime.now() - timedelta(days=date_range_days + 1)
        results = []

        for item in search_result[:max_results * 3]:
            obj = item.get("object", item)
            title = (
                obj.get("title") or
                obj.get("question", {}).get("title") or
                obj.get("name") or ""
            ).strip()
            if not title:
                continue

            url_path = obj.get("url") or obj.get("link") or ""
            if not url_path.startswith("http"):
                url_path = "https://www.zhihu.com" + url_path if url_path.startswith("/") else ""
            if not url_path:
                continue

            snippet = (obj.get("excerpt") or obj.get("content") or "")[:300].strip()
            author = obj.get("author", {}).get("name") or obj.get("author_name") or "知乎"

            # 时间过滤（有 created_time 才过滤）
            created = obj.get("created_time") or obj.get("updated_time") or 0
            if created and datetime.fromtimestamp(created) < cutoff:
                continue

            results.append({
                "title": title,
                "url": url_path,
                "snippet": snippet,
                "source_name": author[:50],
                "pub_date": datetime.fromtimestamp(created).strftime("%Y-%m-%d") if created else "",
                "source_keyword": word,
                "source_channel": "zhihu",
            })
            if len(results) >= max_results:
                break

        return results
    except Exception as e:
        print(f"  [zhihu] {word}: 搜索失败 — {e}")
        return []


# ─── B 站 ─────────────────────────────────────────────────────────────────────

def search_bilibili(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]:
    """用 bilibili-api-python 搜索专栏文章，source_channel='bilibili'。"""
    try:
        from bilibili_api import search

        async def _do_search():
            return await search.search_by_type(
                keyword=word,
                search_type=search.SearchObjectType.ARTICLE,
                page=1,
            )

        try:
            result = asyncio.run(_do_search())
        except RuntimeError:
            # 已有运行中的事件循环（如 Jupyter 环境）
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(_do_search())
            finally:
                loop.close()

        cutoff_ts = int((datetime.now() - timedelta(days=date_range_days + 1)).timestamp())
        items = result.get("result") or result.get("data", {}).get("result") or []

        results = []
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
            if not title:
                continue

            pub_ts = item.get("publish_time") or item.get("ctime") or 0
            if pub_ts and pub_ts < cutoff_ts:
                continue

            article_id = item.get("id") or item.get("cvid") or ""
            url = f"https://www.bilibili.com/read/cv{article_id}" if article_id else ""
            if not url:
                continue

            results.append({
                "title": title,
                "url": url,
                "snippet": (item.get("desc") or "")[:300].strip(),
                "source_name": item.get("author_name") or item.get("mid") or "bilibili",
                "pub_date": datetime.fromtimestamp(pub_ts).strftime("%Y-%m-%d") if pub_ts else "",
                "source_keyword": word,
                "source_channel": "bilibili",
            })
            if len(results) >= max_results:
                break

        return results
    except Exception as e:
        print(f"  [bilibili] {word}: 搜索失败 — {e}")
        return []


# ─── 统一入口 ──────────────────────────────────────────────────────────────────

def search_all_domestic(
    word: str, date_range_days: int = 1, max_results_each: int = 5
) -> list[dict]:
    """
    顺序调用国内通道并合并结果，任一失败不影响其他。

    停用说明（2026-06-08）：知乎 / B站可信度评估不达标，已从调用链移除。
    search_zhihu / search_bilibili 函数体保留在本模块内，可单独调用验证；
    若未来重新启用，只需把它们加回下面的 fn 元组即可，无需重写。
    """
    results = []
    for fn in (search_baidu,):   # 原为 (search_baidu, search_zhihu, search_bilibili)
        results.extend(fn(word, date_range_days=date_range_days, max_results=max_results_each))
        time.sleep(1)   # 礼貌性间隔，避免触发反爬
    return results
