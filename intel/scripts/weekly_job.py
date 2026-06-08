#!/usr/bin/env python3
"""
CIOSH 情报雷达 · 每周任务（6步：统计→退休→新词→更新词库→周报→邮件）
运行方式：cd intel && python3 scripts/weekly_job.py
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_INTEL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_INTEL_DIR))

from config import get_config
from models import get_db, init_db
from services.keyword_evolver import compute_weekly_stats, extract_new_keywords, apply_evolution
from services.role_reporter import synthesize_role_digests, build_unified_html
from services.mailer import send_report
from services.skill_evolver import (
    evolve_layer2_rules, evolve_analyzer_prompt,
    evolve_category_briefs, refresh_skill_summary,
)


def main() -> None:
    cfg = get_config()
    today = datetime.now().strftime("%Y-%m-%d")
    week_label = datetime.now().strftime("%G-W%V")

    init_db()
    conn = get_db()

    try:
        # 幂等：当周已跑过则退出（使用 week_label 避免同周重复运行）
        if conn.execute(
            "SELECT 1 FROM reports WHERE report_date=? AND report_type='weekly'", (week_label,)
        ).fetchone():
            print(f"本周周报已存在（{week_label}），跳过。")
            return

        print(f"=== CIOSH 情报雷达  周任务  {today} ({week_label}) ===")

        # 加载词库
        with open(cfg.KEYWORD_DB_PATH, encoding="utf-8") as f:
            keyword_db = json.load(f)

        # Step 1: 统计本周各关键词产出
        stats = compute_weekly_stats(conn, days=7)
        print(f"Step1: 统计 {len(stats)} 个关键词的本周产出")

        # Step 2 & 3: 退休决策 + 挖掘候选新词
        existing_words = {kw["word"] for kw in keyword_db["keywords"]}
        new_candidates = extract_new_keywords(conn, days=7, existing_words=existing_words)
        print(f"Step3: 新词候选 {len(new_candidates)} 个")

        # Step 4: 更新 keyword_db.json
        keyword_db, retired, added = apply_evolution(keyword_db, stats, new_candidates, today=today)

        # 保存快照到 DB（便于回溯）
        conn.execute("""
            INSERT INTO keyword_snapshots (week_label, snapshot_json, created_at)
            VALUES (?, ?, ?)
        """, (week_label, json.dumps(keyword_db, ensure_ascii=False), today))
        conn.commit()

        # 写回 keyword_db.json（原子写入，防止崩溃导致文件损坏）
        with tempfile.NamedTemporaryFile(
            "w", dir=cfg.KEYWORD_DB_PATH.parent, encoding="utf-8", suffix=".tmp", delete=False
        ) as f:
            json.dump(keyword_db, f, ensure_ascii=False, indent=2)
            tmp_path = f.name
        os.replace(tmp_path, str(cfg.KEYWORD_DB_PATH))

        print(f"Step4: 词库已更新 — 退休 {len(retired)} 个，新增 {len(added)} 个")
        if retired:
            print(f"  退休词：{', '.join(retired)}")
        if added:
            print(f"  新词（Tier3）：{', '.join(added)}")

        # Step 5: 生成周报 HTML（使用统一模板，与日报共用 A/B/C/D 四段结构）
        rows = conn.execute("""
            SELECT title, url, snippet, source_keyword, source_name,
                   category, priority, ciosh_relevance, ciosh_action, summary_zh
            FROM intel_items
            WHERE collected_at >= date('now', '-7 days')
            ORDER BY
                CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                collected_at DESC
            LIMIT 100
        """).fetchall()
        all_items = [dict(r) for r in rows]

        role_digests = synthesize_role_digests(all_items)
        kw_health_data = {word: s for word, s in stats.items()}
        html = build_unified_html(
            all_items, role_digests, week_label,
            kw_health_data=kw_health_data,
            retired=retired,
            new_candidates=added,
            report_kind="weekly",
        )
        high_count = len([i for i in all_items if (i.get("priority") or "").lower() == "high"])
        print(f"Step5: 周报 HTML 生成（高优先级 {high_count} 条，共 {len(all_items)} 条）")

        # 保存到 reports 表（使用 week_label 作为 report_date）
        conn.execute("""
            INSERT INTO reports (report_date, report_type, title_zh, html_body, item_count)
            VALUES (?, 'weekly', ?, ?, ?)
        """, (week_label, f"CIOSH情报周报 {week_label}", html, len(all_items)))
        conn.commit()

        # Step 5-B: Skill 层进化（每步失败不中断）
        skills_dir = _INTEL_DIR / "skills"
        for label, fn, args in [
            ("Layer2规则",     evolve_layer2_rules,     (conn, skills_dir)),
            ("Analyzer提案",   evolve_analyzer_prompt,  (conn, skills_dir)),
            ("品类简报",        evolve_category_briefs,  (conn, skills_dir)),
            ("SKILL.md更新",   refresh_skill_summary,   (conn, cfg.KEYWORD_DB_PATH, skills_dir)),
        ]:
            try:
                print(f"Skill进化：{label}...")
                fn(*args)
            except Exception as e:
                print(f"  Skill进化 [{label}] 失败（不中断）：{e}")

        # Step 6: 发送邮件
        subject = f"[CIOSH情报] {week_label} 周报 · 高优先级 {high_count} 条"
        if added:
            subject += f" · 新词 {len(added)} 个"
        ok = send_report(subject, html)
        if ok:
            conn.execute(
                "UPDATE reports SET sent_at=? WHERE report_date=? AND report_type='weekly'",
                (datetime.now().isoformat(sep=" ", timespec="seconds"), week_label),
            )
            conn.commit()
        print("Step6: 邮件" + ("已发送" if ok else "发送失败（见上方日志）"))
        print(f"=== 完成 ===")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
