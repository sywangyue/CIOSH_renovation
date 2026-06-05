#!/usr/bin/env python3
"""
CIOSH 情报雷达 · 一次性历史回溯采集（仅运行一次）
- 搜索过去 90 天，每个关键词最多取 10 条
- 走完三层漏斗，写入数据库，source_type='seed'
- 不发邮件，只建库
运行方式：cd intel && python3 scripts/seed_job.py
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

_INTEL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_INTEL_DIR))

from config import get_config
from models import get_db, init_db
from services.searcher import search_keyword
from services.layer2_filter import filter_by_layer2
from services.analyzer import batch_analyze


def _layer1_dedup(items: list[dict], conn) -> tuple[list[dict], int]:
    """URL 指纹去重，新 URL 写入 seen_urls。"""
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    new_items, to_insert = [], []
    for item in items:
        url = item.get("url", "")
        h = hashlib.md5(url.encode()).hexdigest()
        if conn.execute("SELECT 1 FROM seen_urls WHERE url_hash=?", (h,)).fetchone():
            continue
        new_items.append(item)
        to_insert.append((h, url, now))
    conn.executemany(
        "INSERT OR IGNORE INTO seen_urls(url_hash,url,first_seen) VALUES(?,?,?)",
        to_insert,
    )
    conn.commit()
    return new_items, len(items) - len(new_items)


def _write_seed_items(items: list[dict], conn) -> int:
    """写入分析结果，source_type='seed'，返回实际写入数。"""
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    written = 0
    for item in items:
        kw_json = json.dumps(item.get("keywords", []), ensure_ascii=False)
        try:
            cur = conn.execute("""
                INSERT OR IGNORE INTO intel_items
                  (title, url, snippet, source_name, pub_date, collected_at,
                   source_keyword, layer2_score, is_analyzed, is_duplicate,
                   category, priority, ciosh_relevance, ciosh_action,
                   summary_zh, keywords_json, analyzed_at, source_type)
                VALUES (?,?,?,?,?,?,?,?,1,0,?,?,?,?,?,?,?,'seed')
            """, (
                item.get("title"), item.get("url"), item.get("snippet"),
                item.get("source_name"), item.get("pub_date"), now,
                item.get("source_keyword"), item.get("layer2_score", 0),
                item.get("category"), item.get("priority"),
                item.get("ciosh_relevance"), item.get("ciosh_action"),
                item.get("summary_zh"), kw_json, item.get("analyzed_at"),
            ))
            if cur.rowcount:
                written += 1
        except Exception as e:
            print(f"  写入跳过：{(item.get('title') or '')[:40]} — {e}")
    conn.commit()
    return written


def main() -> None:
    cfg = get_config()
    init_db()
    conn = get_db()

    # 幂等：已有 seed 数据则跳过
    seed_count = conn.execute(
        "SELECT COUNT(*) FROM intel_items WHERE source_type='seed'"
    ).fetchone()[0]
    if seed_count > 0:
        print(f"Seed 数据已存在（{seed_count} 条），跳过。如需重跑请先清除 seed 数据。")
        conn.close()
        return

    print(f"=== CIOSH 情报雷达  Seed 回溯采集  {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    print("搜索范围：过去 90 天，每词最多 10 条")

    # 加载所有 active 关键词（全 tier）
    with open(cfg.KEYWORD_DB_PATH, encoding="utf-8") as f:
        keyword_db = json.load(f)
    keywords = [kw["word"] for kw in keyword_db["keywords"] if kw["status"] == "active"]
    print(f"关键词：{len(keywords)} 个")

    # 搜索（90天回溯）
    raw_all: list[dict] = []
    for i, kw in enumerate(keywords, 1):
        try:
            results = search_keyword(kw, days_back=90, max_results=10)
            raw_all.extend(results)
            print(f"  [{i}/{len(keywords)}] {kw}: {len(results)} 条")
        except Exception as e:
            print(f"  [{i}/{len(keywords)}] {kw}: 搜索失败 — {e}")
    print(f"原始结果：{len(raw_all)} 条")

    # Layer1 去重
    new_items, duped = _layer1_dedup(raw_all, conn)
    print(f"Layer1 去重：{duped} 条重复 → 剩余 {len(new_items)} 条")

    # Layer2 过滤
    passed_l2, rejected_l2 = filter_by_layer2(new_items)
    print(f"Layer2 过滤：通过 {len(passed_l2)} 条，过滤 {len(rejected_l2)} 条")

    # Layer3 分析（保守上限 20 条，遵守 token 纪律）
    limit = cfg.MAX_LAYER3_PER_DAY
    print(f"Layer3 分析（上限 {limit} 条）...")
    analyzed = batch_analyze(passed_l2, limit=limit)
    print(f"AI 分析完成：{len(analyzed)} 条")

    # 写库
    written = _write_seed_items(analyzed, conn)
    conn.close()

    # 汇总
    print("\n=== Seed 采集完成 ===")
    print(f"  原始：{len(raw_all)} 条")
    print(f"  通过 Layer2：{len(passed_l2)} 条")
    print(f"  AI 分析：{len(analyzed)} 条")
    print(f"  写入数据库：{written} 条")
    high = len([i for i in analyzed if (i.get("priority") or "").lower() == "high"])
    med  = len([i for i in analyzed if (i.get("priority") or "").lower() == "medium"])
    low  = len([i for i in analyzed if (i.get("priority") or "").lower() == "low"])
    print(f"  优先级分布：高 {high} / 中 {med} / 低 {low}")
    print("（无邮件发送，数据已写入 data/ciosh_intel.db）")


if __name__ == "__main__":
    main()
