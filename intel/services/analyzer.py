"""
CIOSH 专属 AI 分析服务：调用 DeepSeek，输出品类信号结构。
_call_deepseek 和 _parse_json_from_text 移植自 Geckos analyzer.py。
"""

import datetime
import json
import sys
from pathlib import Path
from typing import Any

import requests

_INTEL_DIR = Path(__file__).resolve().parent.parent
if str(_INTEL_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEL_DIR))

from config import get_config

# ─── CIOSH 品类体系 ────────────────────────────────────────────────────────────
CIOSH_CATEGORIES = {
    "core_ppe", "ehs_tech", "smart_ppe", "industrial_safety",
    "fire_safety", "env_monitoring", "emergency_response",
    "policy_regulatory", "market_signal", "other",
}

# ─── CIOSH 专属 System Prompt ──────────────────────────────────────────────────
_DEFAULT_SYSTEM_PROMPT = (
    "你是CIOSH（中国国际劳动保护用品交易会）的品类战略顾问，供职于杜塞尔多夫展览（上海）。"
    "你的任务是识别可以帮助CIOSH突破单一PPE品类的战略信号。\n\n"
    "CIOSH当前困境：展商品类过度集中在低端PPE（手套/劳保服/面料），"
    "需要在2027年前引入新品类展商：EHS科技、智慧防护、工业安全系统等方向。\n\n"
    "高优先级信号（直接服务品类引进决策）：\n"
    "- 某细分品类出现新的头部企业或突破性产品\n"
    "- 某细分品类的市场规模/增速数据（佐证引进价值）\n"
    "- 政策法规要求某类新防护设备（创造展商需求）\n"
    "- 竞展（Safety Expo/A+A/CIOSH友展）新增某品类展团\n"
    "- 国内展会/行业协会首次提及某品类方向\n\n"
    "中优先级信号（背景积累，有价值但不紧急）：\n"
    "- 行业技术趋势报告\n"
    "- 企业战略合作或产品发布\n"
    "- 标准/认证变化\n\n"
    "低优先级（噪音，记录但不深度分析）：\n"
    "- 个别企业融资/人事信息\n"
    "- 学术研究\n"
    "- 无明确市场信号的行业动态"
)


def _load_system_prompt() -> str:
    """从 skills/analyzer_prompt/ 读取版本号最大的 .md 文件。缺失时返回默认 prompt。"""
    skills_dir = _INTEL_DIR / "skills" / "analyzer_prompt"
    if not skills_dir.exists():
        return _DEFAULT_SYSTEM_PROMPT
    versions = sorted(skills_dir.glob("v*.md"), key=lambda p: int(p.stem[1:]))
    if not versions:
        return _DEFAULT_SYSTEM_PROMPT
    content = versions[-1].read_text(encoding="utf-8")
    # 文件格式：## System Prompt 之后的内容为 prompt 正文
    if "## System Prompt" in content:
        return content.split("## System Prompt")[-1].strip()
    return content.strip()


# 模块级缓存：每个进程只读一次文件
_SYSTEM_PROMPT = _load_system_prompt()

_VALID_PRIORITIES = {"high", "medium", "low"}
_VALID_RELEVANCE = {"high", "medium", "low"}


def _call_deepseek(system_prompt: str, user_prompt: str) -> str:
    """调用 DeepSeek Chat Completion，返回原始文本。移植自 Geckos analyzer.py。"""
    cfg = get_config()
    if not cfg.DEEPSEEK_API_KEY:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY 配置")
    url = f"{cfg.DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("DeepSeek 返回内容为空")
    return content


def _parse_json_from_text(text: str) -> dict[str, Any]:
    """从模型返回文本中提取 JSON，处理 ```json 包裹。移植自 Geckos analyzer.py。"""
    s = text.strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return json.loads("\n".join(lines).strip())
    return json.loads(s)


def analyze_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    对单条情报调用 DeepSeek 进行 CIOSH 专属分析。
    输入须含 title、snippet（Tavily摘要）、source_keyword。
    输出在原字典基础上补充分析字段，API 失败时用回退值填充。
    """
    result = dict(item)
    title = (item.get("title") or "").strip()
    snippet = (item.get("snippet") or "").strip()
    source_keyword = (item.get("source_keyword") or "").strip()

    user_prompt = (
        f"触发关键词：{source_keyword}\n"
        f"标题：{title}\n"
        f"摘要：{snippet[:500] if snippet else '（无摘要）'}\n\n"
        "请按以下JSON格式输出，不要输出任何其他内容：\n"
        "{\n"
        '  "category": "core_ppe|ehs_tech|smart_ppe|industrial_safety|fire_safety|env_monitoring|emergency_response|policy_regulatory|market_signal|other",\n'
        '  "priority": "high|medium|low",\n'
        '  "summary_zh": "中文一句话（≤30字）",\n'
        '  "ciosh_relevance": "high|medium|low",\n'
        '  "ciosh_action": "可引进展商品类：XXX / 可用于招商话术：XXX / 建议追踪",\n'
        '  "keywords": ["关键词1", "关键词2", "关键词3"],\n'
        '  "new_keyword_suggestion": "建议加入词库的新词（无则填null）"\n'
        "}"
    )

    now_str = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    try:
        raw = _call_deepseek(_SYSTEM_PROMPT, user_prompt)
        parsed = _parse_json_from_text(raw)
    except Exception as e:
        print(f"AI分析失败：{title[:40]}，原因：{e}")
        result.update({
            "category": "other",
            "priority": "low",
            "summary_zh": "AI分析失败",
            "ciosh_relevance": "low",
            "ciosh_action": "",
            "keywords": [],
            "new_keyword_suggestion": None,
            "analyzed_at": now_str,
        })
        return result

    category = (parsed.get("category") or "other").strip()
    if category not in CIOSH_CATEGORIES:
        category = "other"

    priority = (parsed.get("priority") or "low").strip().lower()
    if priority not in _VALID_PRIORITIES:
        priority = "low"

    ciosh_relevance = (parsed.get("ciosh_relevance") or "low").strip().lower()
    if ciosh_relevance not in _VALID_RELEVANCE:
        ciosh_relevance = "low"

    keywords = parsed.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    keywords = [k.strip() for k in keywords if isinstance(k, str)][:5]

    result.update({
        "category": category,
        "priority": priority,
        "summary_zh": (parsed.get("summary_zh") or "").strip(),
        "ciosh_relevance": ciosh_relevance,
        "ciosh_action": (parsed.get("ciosh_action") or "").strip(),
        "keywords": keywords,
        "new_keyword_suggestion": parsed.get("new_keyword_suggestion") or None,
        "analyzed_at": now_str,
    })
    return result


def batch_analyze(items: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """
    批量分析，跳过已标记 is_duplicate=1 的条目。
    每 5 条打印进度，单条失败时跳过继续。
    """
    to_process = [item for item in items if not item.get("is_duplicate", 0)][:limit]
    total = len(to_process)
    results = []
    for idx, item in enumerate(to_process, start=1):
        try:
            results.append(analyze_item(item))
        except Exception as e:
            print(f"分析异常：{(item.get('title') or '')[:40]}，原因：{e}")
        if idx % 5 == 0 or idx == total:
            print(f"已分析 {idx}/{total}")
    return results
