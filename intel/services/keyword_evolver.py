"""
CIOSH 情报雷达 · 关键词进化逻辑
- 计算周级 yield_rate
- 自动退休连续低效词
- 从高优先级结果挖掘新词候选
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_INTEL_DIR = Path(__file__).resolve().parent.parent
if str(_INTEL_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEL_DIR))

_MIN_YIELD_RATE = 0.05
_RETIRE_AFTER_WEEKS = 2
_MIN_NEW_WORD_FREQ = 3


def compute_weekly_stats(conn, days: int = 7) -> dict[str, dict[str, Any]]:
    """
    查询最近 days 天的数据，按 source_keyword 统计：
    total（总命中）/ quality（高中优先级）/ yield_rate。
    返回 {keyword: {total, quality, yield_rate}}
    """
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT source_keyword,
               COUNT(*) AS total,
               SUM(CASE WHEN priority IN ('high','medium') THEN 1 ELSE 0 END) AS quality
        FROM intel_items
        WHERE collected_at >= ? AND source_keyword IS NOT NULL
        GROUP BY source_keyword
    """, (since,)).fetchall()

    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        total = row["total"] or 0
        quality = row["quality"] or 0
        stats[row["source_keyword"]] = {
            "total": total,
            "quality": quality,
            "yield_rate": round(quality / total, 4) if total > 0 else 0.0,
        }
    return stats


def extract_new_keywords(
    conn, days: int = 7, existing_words: set[str] | None = None
) -> list[str]:
    """
    从最近 days 天的 high 优先级条目 keywords_json 字段提取高频词。
    返回频次 >= _MIN_NEW_WORD_FREQ 且不在现有词库中的词列表。
    """
    existing_words = existing_words or set()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT keywords_json FROM intel_items
        WHERE priority = 'high' AND collected_at >= ?
          AND keywords_json IS NOT NULL AND keywords_json != '[]'
    """, (since,)).fetchall()

    freq: dict[str, int] = {}
    for row in rows:
        try:
            words = json.loads(row["keywords_json"])
        except Exception:
            continue
        for w in words:
            if isinstance(w, str) and w.strip():
                freq[w.strip()] = freq.get(w.strip(), 0) + 1

    return [w for w, cnt in freq.items() if cnt >= _MIN_NEW_WORD_FREQ and w not in existing_words]


def apply_evolution(
    keyword_db: dict[str, Any],
    stats: dict[str, dict],
    new_candidates: list[str],
    today: str | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    将本周统计应用到词库：
      - 更新每个关键词的 yield_rate 和 low_yield_weeks 计数
      - 连续 _RETIRE_AFTER_WEEKS 周低效 → status=retired
      - 将候选新词写入为 Tier 3
      - 更新 version / last_updated / evolution_log

    返回 (updated_keyword_db, retired_words, added_words)
    CLAUDE.md 约束：修改 keyword_db 必须更新 version 和 last_updated。
    """
    today = today or datetime.now().strftime("%Y-%m-%d")
    retired: list[str] = []
    added: list[str] = []

    for kw in keyword_db["keywords"]:
        word = kw["word"]
        s = stats.get(word)
        if s is None:
            continue

        kw["yield_rate"] = s["yield_rate"]

        if s["yield_rate"] < _MIN_YIELD_RATE:
            kw["low_yield_weeks"] = kw.get("low_yield_weeks", 0) + 1
            if kw["low_yield_weeks"] >= _RETIRE_AFTER_WEEKS and kw["status"] == "active":
                kw["status"] = "retired"
                retired.append(word)
        else:
            kw["low_yield_weeks"] = 0  # 产出恢复则重置连续低效计数

    # 写入新词（tier=3，added_by="auto"）
    existing_words = {kw["word"] for kw in keyword_db["keywords"]}
    for word in new_candidates:
        if word not in existing_words:
            keyword_db["keywords"].append({
                "word": word,
                "category": "other",
                "tier": 3,
                "lang": "zh",
                "added_at": today,
                "added_by": "auto",
                "hit_count_total": 0,
                "hit_count_quality": 0,
                "yield_rate": 0.0,
                "low_yield_weeks": 0,
                "last_hit": None,
                "status": "active",
            })
            existing_words.add(word)
            added.append(word)

    # 记录进化日志
    if retired or added:
        reasons = []
        if retired:
            reasons.append(f"yield_rate < {_MIN_YIELD_RATE} 连续 {_RETIRE_AFTER_WEEKS} 周退休")
        if added:
            reasons.append("auto_new_word")
        keyword_db.setdefault("evolution_log", []).append({
            "date": today,
            "added": added,
            "retired": retired,
            "reason": "; ".join(reasons),
        })

    # CLAUDE.md 约束：修改必须更新 version 和 last_updated
    keyword_db["last_updated"] = today
    keyword_db["version"] = datetime.now().strftime("%G-W%V")

    return keyword_db, retired, added
