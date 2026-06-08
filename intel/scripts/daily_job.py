#!/usr/bin/env python3
"""
CIOSH 情报雷达 · 每日任务（8步流程）
运行方式：cd intel && python3 scripts/daily_job.py
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

_INTEL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_INTEL_DIR))

from config import get_config
from models import get_db, init_db
from services.searcher import search_keywords
from services.domestic_searcher import search_all_domestic
from services.layer2_filter import filter_by_layer2
from services.analyzer import batch_analyze
from services.role_reporter import synthesize_role_digests, build_unified_html
from services.mailer import send_report


MAX_PUB_AGE_DAYS = 7  # 发布日期超过此天数的文章将被过滤

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
    """URL 指纹去重：过滤批次内重复及已见 URL，新 URL 写入 seen_urls。"""
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    new_items, to_insert = [], []
    seen_in_batch: set[str] = set()
    for item in items:
        url = item.get("url", "")
        h = hashlib.md5(url.encode()).hexdigest()
        if h in seen_in_batch:
            continue
        if conn.execute("SELECT 1 FROM seen_urls WHERE url_hash=?", (h,)).fetchone():
            continue
        seen_in_batch.add(h)
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
        except sqlite3.IntegrityError:
            pass
        except Exception as e:
            print(f"  写入错误：{(item.get('title') or '')[:40]} — {e}")
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
    db["version"] = datetime.now().strftime("%Y-%m-%d")
    with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", suffix=".tmp", delete=False) as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, str(path))


def _parse_pub_date(pub_date: str, url: str) -> datetime | None:
    """
    尝试从 pub_date 字符串解析日期；若为空则从 URL 路径中提取 YYYYMM 或 YYYY-MM-DD 模式。
    返回 naive datetime（本地时区），无法解析时返回 None。
    """
    raw = (pub_date or "").strip()
    if raw:
        # ISO 8601 格式
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        # RFC 822 格式（Tavily 返回的 "Sun, 07 Jun 2026 22:11:35 GMT"）
        try:
            dt = parsedate_to_datetime(raw)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            pass

    # pub_date 为空时，从 URL 路径中提取日期（政府/新闻网站常见模式）
    # 匹配 /YYYYMMDD/ 或 /YYYYMM/ 路径片段，要求年份 2000–2099
    m = re.search(r"/20(\d{2})(0[1-9]|1[0-2])(\d{2})/", url)
    if m:
        try:
            return datetime(int("20" + m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r"/20(\d{2})(0[1-9]|1[0-2])/", url)
    if m:
        return datetime(int("20" + m.group(1)), int(m.group(2)), 1)

    return None


def _filter_by_pub_date(items: list[dict]) -> tuple[list[dict], int]:
    """
    过滤发布日期超过 MAX_PUB_AGE_DAYS 天的条目。

    日期来源优先级：
    1. pub_date 字段（ISO 8601 或 RFC 822）
    2. URL 路径中的 YYYYMMDD 或 YYYYMM 模式（政府/新闻站常见）
    3. 两者均无法解析时：保留（宁可误收，不漏真新闻）
    """
    cutoff = datetime.now() - timedelta(days=MAX_PUB_AGE_DAYS)
    fresh, stale_count = [], 0
    for item in items:
        parsed = _parse_pub_date(item.get("pub_date", ""), item.get("url", ""))
        if parsed is None:
            fresh.append(item)
        elif parsed >= cutoff:
            fresh.append(item)
        else:
            stale_count += 1
    return fresh, stale_count


# ─── 主流程 ────────────────────────────────────────────────────────────────────

def main() -> None:
    cfg = get_config()
    today = datetime.now().strftime("%Y-%m-%d")
    report_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    init_db()
    conn = get_db()

    try:
        # 幂等：当天已跑过则退出
        if conn.execute(
            "SELECT 1 FROM reports WHERE report_date=? AND report_type='daily'", (today,)
        ).fetchone():
            print(f"今日日报已存在（{today}），跳过。")
            return

        print(f"=== CIOSH 情报雷达  日任务  {today} ===")

        # Step 1: 加载关键词库
        keywords, keyword_db = _load_keywords(cfg.KEYWORD_DB_PATH)
        print(f"Step1: {len(keywords)} 个关键词（{'含Tier3，周一' if datetime.now().weekday()==0 else 'Tier1+2'}）")

        # Step 2: 多通道搜索（Tavily 国际 + 百度新闻）
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

        # Step 2.5: 发布日期过滤（MAX_PUB_AGE_DAYS=7，无法解析日期的保留）
        raw_results, stale_count = _filter_by_pub_date(raw_results)
        if stale_count:
            print(f"Step2.5: 过期文章过滤 {stale_count} 条 → 剩余 {len(raw_results)} 条")

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

        # Step 5: Layer3 分桶限额（Tavily 桶 ≤ LAYER3_CAP_TAVILY / 国内桶 ≤ LAYER3_CAP_DOMESTIC）
        # 各桶内按 layer2_score 降序竞争，保证中英文信号均衡进入分析
        tavily_bucket = sorted(
            [i for i in passed_l2 if i.get("source_channel", "tavily") == "tavily"],
            key=lambda x: x.get("layer2_score", 0), reverse=True
        )[:cfg.LAYER3_CAP_TAVILY]
        domestic_bucket = sorted(
            [i for i in passed_l2 if i.get("source_channel", "tavily") != "tavily"],
            key=lambda x: x.get("layer2_score", 0), reverse=True
        )[:cfg.LAYER3_CAP_DOMESTIC]
        to_analyze = tavily_bucket + domestic_bucket
        print(f"Step5 Layer3: Tavily {len(tavily_bucket)} 条 + 国内 {len(domestic_bucket)} 条 = {len(to_analyze)} 条进入分析...")
        analyzed = batch_analyze(to_analyze)
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

        high_count = len([i for i in analyzed if (i.get("priority") or "").lower() == "high"])
        med_count  = len([i for i in analyzed if (i.get("priority") or "").lower() == "medium"])
        low_count  = len([i for i in analyzed if (i.get("priority") or "").lower() == "low"])

        # Step 6.5: 角色摘要（单次 DeepSeek 调用，失败降级为空摘要不阻断）
        role_digests = synthesize_role_digests(analyzed)

        # Step 7: 生成统一日报 HTML（含 Part D 当日关键词命中快照 Top 20）
        total_analyzed_by_kw: dict[str, int] = {}
        for item in analyzed:
            kw = item.get("source_keyword", "")
            if kw:
                total_analyzed_by_kw[kw] = total_analyzed_by_kw.get(kw, 0) + 1
        kw_health_data = {
            word: {
                "total": total,
                "quality": quality_by_kw.get(word, 0),
                "yield_rate": quality_by_kw.get(word, 0) / total if total > 0 else 0.0,
            }
            for word, total in sorted(total_analyzed_by_kw.items(), key=lambda x: x[1], reverse=True)[:20]
        }
        html = build_unified_html(
            analyzed, role_digests, today,
            kw_health_data=kw_health_data,
            retired=[],
            new_candidates=[],
            report_kind="daily",
        )

        conn.execute("""
            INSERT INTO reports (report_date, report_type, title_zh, html_body, item_count)
            VALUES (?, 'daily', ?, ?, ?)
        """, (today, f"CIOSH情报日报 {report_date}", html, len(analyzed)))
        conn.commit()
        print(f"Step7: 日报 HTML 生成完成（高{high_count} 中{med_count} 低{low_count}）")

        # Step 8: 发送统一邮件（MAIL_TO + MAIL_CC，无三路分发）
        subject = f"[CIOSH情报] {today} · {len(analyzed)}条"
        ok = send_report(subject, html)
        if ok:
            conn.execute(
                "UPDATE reports SET sent_at=? WHERE report_date=? AND report_type='daily'",
                (datetime.now().isoformat(sep=" ", timespec="seconds"), today),
            )
            conn.commit()
        print("Step8: 邮件" + ("已发送" if ok else "发送失败（见上方日志）"))
        print(f"=== 完成 ===")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
