"""
Layer2 标题相关性评分：纯本地规则，0 token。

评分规则：
  +2  标题含 CIOSH 品类词（安全、防护、EHS、PPE 等领域核心词）
  +1  标题含行业信号词（展会、市场、技术、法规等）
  -2  标题含噪音词（招聘、促销、广告等）
  通过阈值 = config.LAYER2_MIN_SCORE（默认 1）
"""

import json
import sys
from pathlib import Path
from typing import Any

_INTEL_DIR = Path(__file__).resolve().parent.parent
if str(_INTEL_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEL_DIR))

from config import get_config


def _load_rules() -> dict | None:
    """从 skills/layer2_rules/ 读取版本号最大的 .json 文件。缺失时返回 None。"""
    skills_dir = _INTEL_DIR / "skills" / "layer2_rules"
    if not skills_dir.exists():
        return None
    versions = sorted(skills_dir.glob("v*.json"), key=lambda p: int(p.stem[1:]))
    if not versions:
        return None
    with open(versions[-1], encoding="utf-8") as f:
        return json.load(f)


# 模块级缓存：每个进程只读一次文件
_rules = _load_rules()

# ─── 品类核心词：命中任意一个 +2 ──────────────────────────────────────────────
_CATEGORY_TERMS_DEFAULT = [
    # 中文
    "EHS", "PPE", "劳保", "安全帽", "防护服", "工业安全", "安全生产",
    "职业健康", "可穿戴", "智能安全", "安全传感", "传感器", "消防",
    "应急", "监测仪", "气体检测", "防坠落", "高空作业", "危化品",
    "职业病", "安全设备", "防护装备", "噪声防护", "环境监测", "防护",
    # 英文
    "safety", "protective", "hazard", "occupational", "wearable",
    "fall protection", "fire protection",
]

# ─── 行业信号词：命中任意一个 +1 ──────────────────────────────────────────────
_SIGNAL_TERMS_DEFAULT = [
    # 中文
    "展会", "展览", "展商", "市场", "技术", "系统", "解决方案",
    "标准", "认证", "法规", "政策", "行业", "趋势", "新型", "创新",
    "智慧工厂", "物联网", "采购", "产品发布",
    # 英文
    "exhibition", "market", "technology", "solution", "innovation",
    "standard", "regulation", "industry", "report", "trend",
]

# ─── 噪音词：命中任意一个 -2 ──────────────────────────────────────────────────
_NOISE_TERMS_DEFAULT = [
    # 中文
    "招聘", "招募", "求职", "校招", "社招", "薪资", "待遇",
    "优惠", "折扣", "促销", "推广", "广告", "经销", "黄页",
    "专利转让", "商标注册",
    # 英文
    "hiring", "apply now", "discount", "promotion",
]
# ─── 从 Skill 文件加载，缺失则用默认值 ───────────────────────────────────────
_CATEGORY_TERMS = _rules["category_terms"] if _rules else _CATEGORY_TERMS_DEFAULT
_SIGNAL_TERMS   = _rules["signal_terms"]   if _rules else _SIGNAL_TERMS_DEFAULT
_NOISE_TERMS    = _rules["noise_terms"]    if _rules else _NOISE_TERMS_DEFAULT
# ──────────────────────────────────────────────────────────────────────────────


def score_title(title: str) -> float:
    """对单条标题打分，返回相关性分值（可为负）。"""
    t = title.lower()
    score = 0.0
    if any(term.lower() in t for term in _CATEGORY_TERMS):
        score += 2
    if any(term.lower() in t for term in _SIGNAL_TERMS):
        score += 1
    if any(term.lower() in t for term in _NOISE_TERMS):
        score -= 2
    return score


def filter_by_layer2(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    对搜索结果打分并分类。
    返回 (passed, rejected)，每个条目均添加 layer2_score 字段。
    """
    cfg = get_config()
    min_score = cfg.LAYER2_MIN_SCORE
    passed, rejected = [], []
    for item in items:
        s = score_title(item.get("title", ""))
        tagged = {**item, "layer2_score": s}
        (passed if s >= min_score else rejected).append(tagged)
    return passed, rejected
