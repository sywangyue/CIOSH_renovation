#!/usr/bin/env python3
"""
CIOSH 情报雷达 · 每日任务（8步流程）
运行方式：cd intel && python3 scripts/daily_job.py
"""

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

_INTEL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_INTEL_DIR))

from config import get_config
from models import get_db, init_db
from services.searcher import search_keywords
from services.domestic_searcher import search_all_domestic
from services.layer2_filter import filter_by_layer2
from services.analyzer import batch_analyze
from services.reporter import build_daily_html
from services.mailer import send_report


# ─── 辅助函数 ──────────────────────────────────────────────────────────────────

def _load_keywords(path: Path) -> tuple[list[str], dict]:
    """加载词库，返回 (今日搜索词列表, 原始词库 dict)。周一额外包含 tier3。"""
    with open(path, encoding="utf-8") as f:
        db = json.load(f)
    is_monday = datetime.now().weekday() == 0
    active = [
        kw for kw in db["keywords"]
        if kw["status"] == "active"
        and (kw["tier"] in (1, 2) or (is_monday and kw["tier"] == 3))
    ]
    return [kw["word"] for kw in active], db


def _layer1_dedup(items: list[dict], conn) -> tuple[list[dict], int]:
    """URL 指纹去重：过滤已见 URL，新 URL 写入 seen_urls。"""
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


def _write_intel_items(items: list[dict], conn) -> None:
    """将分析结果批量写入 intel_items，URL 冲突时跳过。"""
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    for item in items:
        kw_json = json.dumps(item.get("keywords", []), ensure_ascii=False)
        try:
            conn.execute("""
                INSERT OR IGNORE INTO intel_items
                  (title, url, snippet, source_name, pub_date, collected_at,
                   source_keyword, source_channel, layer2_score, is_analyzed, is_duplicate,
                   category, priority, ciosh_relevance, ciosh_action,
                   summary_zh, keywords_json, analyzed_at, source_type)
                VALUES (?,?,?,?,?,?,?,?,?,1,0,?,?,?,?,?,?,?,'daily')
            """, (
                item.get("title"), item.get("url"), item.get("snippet"),
                item.get("source_name"), item.get("pub_date"), now,
                item.get("source_keyword"), item.get("source_channel", "tavily"),
                item.get("layer2_score", 0),
                item.get("category"), item.get("priority"),
                item.get("ciosh_relevance"), item.get("ciosh_action"),
                item.get("summary_zh"), kw_json, item.get("analyzed_at"),
            ))
        except Exception as e:
            print(f"  写入跳过：{(item.get('title') or '')[:40]} — {e}")
    conn.commit()


def _update_keyword_hits(
    db: dict,
    results_by_kw: dict[str, int],
    quality_by_kw: dict[str, int],
    path: Path,
) -> None:
    """更新 hit_count_total / hit_count_quality / last_hit，写回 keyword_db.json。"""
    today = datetime.now().strftime("%Y-%m-%d")
    for kw in db["keywords"]:
        word = kw["word"]
        if word in results_by_kw:
            kw["hit_count_total"] += results_by_kw[word]
            kw["hit_count_quality"] += quality_by_kw.get(word, 0)
            kw["last_hit"] = today
    db["last_updated"] = today
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ─── 主流程 ────────────────────────────────────────────────────────────────────

def main() -> None:
    cfg = get_config()
    today = datetime.now().strftime("%Y-%m-%d")
    report_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    init_db()
    conn = get_db()

    # 幂等：当天已跑过则退出
    if conn.execute(
        "SELECT 1 FROM reports WHERE report_date=? AND report_type='daily'", (today,)
    ).fetchone():
        print(f"今日日报已存在（{today}），跳过。")
        conn.close()
        return

    print(f"=== CIOSH 情报雷达  日任务  {today} ===")

    # Step 1: 加载关键词库
    keywords, keyword_db = _load_keywords(cfg.KEYWORD_DB_PATH)
    print(f"Step1: {len(keywords)} 个关键词（{'含Tier3，周一' if datetime.now().weekday()==0 else 'Tier1+2'}）")

    # Step 2: 多通道搜索（Tavily 国际 + 国内三通道）
    print("Step2: 多通道搜索...")
    tavily_results = search_keywords(keywords, days_back=1)
    domestic_results = []
    for kw in keywords:
        domestic_results.extend(search_all_domestic(kw, date_range_days=1, max_results_each=3))
    raw_results = tavily_results + domestic_results
    print(f"  Tavily {len(tavily_results)} 条 + 国内通道 {len(domestic_results)} 条 = {len(raw_results)} 条")

    results_by_kw: dict[str, int] = {}
    for item in raw_results:
        kw = item.get("source_keyword", "")
        results_by_kw[kw] = results_by_kw.get(kw, 0) + 1

    # Step 3: Layer1 URL 去重
    new_items, duped = _layer1_dedup(raw_results, conn)
    print(f"Step3 Layer1: 去重 {duped} 条 → 剩余 {len(new_items)} 条")

    # Step 4: Layer2 标题评分
    passed_l2, rejected_l2 = filter_by_layer2(new_items)
    # 按 layer2_score 降序，确保最相关的条目优先进入 Layer3（不论来源通道）
    passed_l2.sort(key=lambda x: x.get("layer2_score", 0), reverse=True)
    channels = {}
    for i in passed_l2:
        ch = i.get("source_channel", "tavily")
        channels[ch] = channels.get(ch, 0) + 1
    print(f"Step4 Layer2: 通过 {len(passed_l2)} 条，过滤 {len(rejected_l2)} 条 | 通道分布: {channels}")

    # Step 5: Layer3 DeepSeek 分析
    limit = cfg.MAX_LAYER3_PER_DAY
    print(f"Step5 Layer3: 分析（上限 {limit} 条）...")
    analyzed = batch_analyze(passed_l2, limit=limit)
    print(f"  完成 {len(analyzed)} 条")

    # 统计高质量命中（priority = high / medium → 计入词库质量数）
    quality_by_kw: dict[str, int] = {}
    for item in analyzed:
        if (item.get("priority") or "").lower() in ("high", "medium"):
            kw = item.get("source_keyword", "")
            quality_by_kw[kw] = quality_by_kw.get(kw, 0) + 1

    # Step 6: 写入数据库 + 更新词库
    _write_intel_items(analyzed, conn)
    _update_keyword_hits(keyword_db, results_by_kw, quality_by_kw, cfg.KEYWORD_DB_PATH)
    print(f"Step6: 写入 {len(analyzed)} 条，词库 last_updated 已更新")

    # Step 7: 生成日报 HTML
    stats = {
        "keywords": len(keywords),
        "raw": len(raw_results),
        "passed_layer2": len(passed_l2),
        "analyzed": len(analyzed),
    }
    html = build_daily_html(analyzed, stats, report_date)

    high_count = len([i for i in analyzed if (i.get("priority") or "").lower() == "high"])
    med_count  = len([i for i in analyzed if (i.get("priority") or "").lower() == "medium"])
    low_count  = len([i for i in analyzed if (i.get("priority") or "").lower() == "low"])

    conn.execute("""
        INSERT INTO reports (report_date, report_type, title_zh, html_body, item_count)
        VALUES (?, 'daily', ?, ?, ?)
    """, (today, f"CIOSH情报日报 {report_date}", html, len(analyzed)))
    conn.commit()
    print(f"Step7: 日报 HTML 生成完成（高{high_count} 中{med_count} 低{low_count}）")

    # Step 8: 发送邮件
    subject = f"[CIOSH情报] {report_date} 日报 · {len(analyzed)} 条新情报"
    if high_count:
        subject += f"（{high_count} 条高优先级）"
    ok = send_report(subject, html)
    if ok:
        conn.execute(
            "UPDATE reports SET sent_at=? WHERE report_date=? AND report_type='daily'",
            (datetime.now().isoformat(sep=" ", timespec="seconds"), today),
        )
        conn.commit()
    print("Step8: 邮件" + ("已发送" if ok else "发送失败（见上方日志）"))

    conn.close()
    print(f"=== 完成 ===")


if __name__ == "__main__":
    main()
