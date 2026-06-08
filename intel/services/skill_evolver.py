"""
CIOSH 情报雷达 · Skill 进化层
四个函数由 weekly_job.py 在关键词进化之后依次调用。
任何函数失败均打印错误后返回，不中断 weekly_job。
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_INTEL_DIR = Path(__file__).resolve().parent.parent
if str(_INTEL_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEL_DIR))


def _atomic_json_write(path: Path, data: dict) -> None:
    """写入 JSON 文件，使用临时文件 + os.replace 保证原子性。"""
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, encoding="utf-8", suffix=".tmp", delete=False
    ) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, str(path))


def _load_evolver_state(skills_dir: Path) -> dict:
    state_path = skills_dir / "_evolver_state.json"
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_evolver_state(skills_dir: Path, state: dict) -> None:
    _atomic_json_write(skills_dir / "_evolver_state.json", state)


# ─── 第二层：Filter Skill ──────────────────────────────────────────────────────

def evolve_layer2_rules(conn, skills_dir: Path) -> None:
    """
    统计本周 layer2_score × priority 交叉频次，
    连续 3 周有效命中率 < 0.2 的词类降权，写入新版本 v{n+1}.json。
    数据门槛：本周分析条目 < 10 则跳过。
    """
    rules_dir = skills_dir / "layer2_rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT layer2_score, priority FROM intel_items
        WHERE is_analyzed=1 AND collected_at >= ?
    """, (since,)).fetchall()

    if len(rows) < 10:
        print(f"  [skill_evolver] Layer2: 本周分析条目 {len(rows)} < 10，跳过")
        return

    # 读取当前版本
    versions = sorted(rules_dir.glob("v*.json"), key=lambda p: int(p.stem[1:]) if p.stem[1:].isdigit() else -1)
    if not versions:
        print("  [skill_evolver] Layer2: 找不到规则文件，跳过")
        return
    with open(versions[-1], encoding="utf-8") as f:
        current = json.load(f)

    # 统计：分数 >= 2 的条目中 high/medium 占比（有效命中率）
    high_med = sum(1 for r in rows if r["layer2_score"] >= 2 and r["priority"] in ("high", "medium"))
    total_high_score = sum(1 for r in rows if r["layer2_score"] >= 2)
    effective_rate = high_med / total_high_score if total_high_score > 0 else 0.0

    # 读取连续低效周数（存储在 skills/_evolver_state.json，避免污染规则文件）
    state = _load_evolver_state(skills_dir)
    low_weeks = state.get("layer2_consecutive_low_weeks", 0)
    if effective_rate < 0.2:
        low_weeks += 1
    else:
        low_weeks = 0
    state["layer2_consecutive_low_weeks"] = low_weeks
    _save_evolver_state(skills_dir, state)

    if low_weeks < 3:
        print(f"  [skill_evolver] Layer2: 有效命中率 {effective_rate:.1%}，连续低效 {low_weeks}/3 周")
        return

    # 达到 3 周：写入降权版本
    new_version = int(versions[-1].stem[1:]) + 1
    new_rules = dict(current)
    new_rules["version"] = new_version
    new_rules["generated_at"] = datetime.now().strftime("%Y-%m-%d")
    new_rules["evolution_note"] = (
        f"v{new_version}: signal_terms 连续3周有效命中率 {effective_rate:.1%} < 20%，"
        f"已记录待人工审核（自动版本保存）"
    )
    new_rules.setdefault("evolution_log", []).append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "effective_rate": round(effective_rate, 4),
        "action": "version_bump_low_effective_rate",
    })
    # 重置状态计数
    state["layer2_consecutive_low_weeks"] = 0
    _save_evolver_state(skills_dir, state)

    new_path = rules_dir / f"v{new_version}.json"
    _atomic_json_write(new_path, new_rules)
    print(f"  [skill_evolver] Layer2: 写入 {new_path.name}（有效命中率 {effective_rate:.1%}）")


# ─── 第三层：Analyzer Skill ────────────────────────────────────────────────────

def evolve_analyzer_prompt(conn, skills_dir: Path) -> None:
    """
    提取本周高/低优先级样本，调用 DeepSeek 生成 ≤3 条 prompt 优化建议，
    写入 skills/analyzer_prompt/proposals/YYYY-WXX.md。
    数据门槛：high 条目 < 3 则跳过。
    """
    from services.analyzer import _call_deepseek

    proposals_dir = skills_dir / "analyzer_prompt" / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    high_rows = conn.execute("""
        SELECT title, ciosh_action, keywords_json FROM intel_items
        WHERE priority='high' AND collected_at >= ? LIMIT 10
    """, (since,)).fetchall()

    if len(high_rows) < 3:
        print(f"  [skill_evolver] Analyzer: 本周 high 条目 {len(high_rows)} < 3，跳过")
        return

    overest_rows = conn.execute("""
        SELECT title FROM intel_items
        WHERE priority='low' AND layer2_score >= 2 AND collected_at >= ? LIMIT 5
    """, (since,)).fetchall()

    high_text = "\n".join(
        f"- {r['title']} | 行动：{r['ciosh_action'] or '无'}"
        for r in high_rows
    )
    over_text = "\n".join(f"- {r['title']}" for r in overest_rows) or "（无）"

    user_prompt = (
        f"以下是本周 CIOSH 情报雷达的分析样本。\n\n"
        f"【高优先级条目（判断正确）】\n{high_text}\n\n"
        f"【被高估条目（Layer2 通过但 AI 判为 low）】\n{over_text}\n\n"
        "请针对当前 System Prompt，输出 ≤3 条具体的优化建议。\n"
        "格式：每条建议一段，以 1. 2. 3. 编号，≤100字/条，聚焦判断规则而非措辞。"
    )

    system = "你是 CIOSH 情报系统的 Prompt 工程师，专注提升分析准确性。"

    try:
        raw = _call_deepseek(system, user_prompt)
    except Exception as e:
        print(f"  [skill_evolver] Analyzer: DeepSeek 调用失败 — {e}")
        return

    raw = raw[:2000]  # 防止异常长响应写入大文件

    week_label = datetime.now().strftime("%G-W%V")
    out_path = proposals_dir / f"{week_label}.md"
    out_path.write_text(
        f"# Analyzer Prompt 优化提案 — {week_label}\n"
        f"> 自动生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"> 审核后手动创建 skills/analyzer_prompt/v{{n+1}}.md 生效\n\n"
        f"## AI 建议\n\n{raw}\n\n"
        f"## 本周高优先级样本\n\n{high_text}\n\n"
        f"## 被高估样本\n\n{over_text}\n",
        encoding="utf-8",
    )
    print(f"  [skill_evolver] Analyzer: 提案已写入 {out_path.name}")


# ─── 第四层：Category Skill ────────────────────────────────────────────────────

def evolve_category_briefs(conn, skills_dir: Path) -> None:
    """
    对本周 high+medium 条目数 >= 3 的品类生成增量摘要（DeepSeek ≤100字），
    追加到 skills/category_briefs/{category}.md。
    每 4 周（week % 4 == 0）做全文浓缩重写。
    """
    from services.analyzer import _call_deepseek

    briefs_dir = skills_dir / "category_briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)

    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    week_label = datetime.now().strftime("%G-W%V")
    week_num = int(datetime.now().strftime("%V"))

    rows = conn.execute("""
        SELECT category, title, summary_zh FROM intel_items
        WHERE priority IN ('high','medium')
          AND collected_at >= ?
          AND category IS NOT NULL AND category != 'other'
    """, (since,)).fetchall()

    # 按品类分组
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(dict(r))

    for cat, items in by_cat.items():
        if len(items) < 3:
            continue

        titles_text = "\n".join(f"- {i['title']}：{i['summary_zh'] or ''}" for i in items[:10])
        try:
            summary = _call_deepseek(
                "你是 CIOSH 品类分析师，用简洁中文总结本周品类信号。",
                f"品类：{cat}\n本周新增情报：\n{titles_text}\n\n请用≤100字总结本周该品类的核心信号。",
            )
        except Exception as e:
            print(f"  [skill_evolver] Category {cat}: DeepSeek 失败 — {e}")
            continue

        summary = summary[:500]  # 防止异常长响应写入大文件

        brief_path = briefs_dir / f"{cat}.md"

        # 每 4 周做浓缩重写（保留近 4 周内容，其余浓缩为一段）
        if week_num % 4 == 0 and brief_path.exists():
            existing = brief_path.read_text(encoding="utf-8")
            try:
                condensed = _call_deepseek(
                    "你是 CIOSH 品类分析师。",
                    f"以下是 {cat} 品类的历史简报，请浓缩为≤200字的结构化摘要：\n\n{existing[:2000]}",
                )
                condensed = condensed[:500]  # 防止异常长响应
                brief_path.write_text(
                    f"# {cat} · 品类情报简报\n\n"
                    f"## 月度浓缩（截至 {week_label}）\n{condensed}\n\n"
                    f"## 周度增量\n### {week_label}\n{summary.strip()}\n\n",
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"  [skill_evolver] Category {cat}: 月度浓缩失败 — {e}")
                _append_to_brief(brief_path, week_label, summary, cat)
        else:
            _append_to_brief(brief_path, week_label, summary, cat)

        print(f"  [skill_evolver] Category {cat}: 简报已更新")


def _append_to_brief(path: Path, week_label: str, summary: str, cat: str) -> None:
    header = f"# {cat} · 品类情报简报\n\n## 周度增量\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        path.write_text(existing + f"### {week_label}\n{summary.strip()}\n\n", encoding="utf-8")
    else:
        path.write_text(header + f"### {week_label}\n{summary.strip()}\n\n", encoding="utf-8")


# ─── SKILL.md 神经中枢 ────────────────────────────────────────────────────────

def refresh_skill_summary(conn, keyword_db_path: Path, skills_dir: Path) -> None:
    """覆写 skills/SKILL.md，更新系统当前能力状态快照。"""
    import json as _json

    week_label = datetime.now().strftime("%G-W%V")

    # 统计数字
    intel_count = conn.execute("SELECT COUNT(*) FROM intel_items").fetchone()[0]
    seen_count  = conn.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0]

    with open(keyword_db_path, encoding="utf-8") as f:
        kdb = _json.load(f)
    active_kw = sum(1 for k in kdb["keywords"] if k["status"] == "active")

    # 当前 prompt 版本
    prompt_dir = skills_dir / "analyzer_prompt"
    versions = sorted(prompt_dir.glob("v*.md"), key=lambda p: int(p.stem[1:]) if p.stem[1:].isdigit() else -1)
    prompt_ver = versions[-1].name if versions else "v1.md（未找到）"

    # 本周品类热度
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    cat_rows = conn.execute("""
        SELECT category, COUNT(*) as cnt FROM intel_items
        WHERE collected_at >= ? AND category IS NOT NULL
        GROUP BY category ORDER BY cnt DESC LIMIT 5
    """, (since,)).fetchall()
    cat_lines = "\n".join(f"  {r['category']}: {r['cnt']} 条" for r in cat_rows) or "  （暂无数据）"

    # 本周词库变动
    evo_log = kdb.get("evolution_log", [])
    last_evo = evo_log[-1] if evo_log else None
    evo_text = (
        f"  新增：{last_evo['added']}  退休：{last_evo['retired']}" if last_evo else "  （本周无变动）"
    )

    # 最新 proposal 文件
    proposals_dir = skills_dir / "analyzer_prompt" / "proposals"
    proposals = sorted(proposals_dir.glob("*.md")) if proposals_dir.exists() else []
    proposal_link = f"  待审核：{proposals[-1].name}" if proposals else "  （暂无提案）"

    skill_md = f"""# CIOSH Intel Radar · Skill 状态摘要

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}（{week_label}）
> 下次自动更新：下周一 03:30（weekly_job.py 自动覆写本文件）

---

## 系统数据状态

| 指标 | 值 |
|---|---|
| 累计情报条目 | {intel_count} 条 |
| URL 指纹库 | {seen_count} 条 |
| 活跃关键词 | {active_kw} 个 |
| 当前 Analyzer Prompt | {prompt_ver} |

---

## 本周品类热度（按情报密度）

{cat_lines}

---

## 词库本周变动

{evo_text}

---

## Analyzer Prompt 提案

{proposal_link}

---

## 进入本项目必读文件

1. `CLAUDE.md` — 硬性约束
2. `skills/SKILL.md`（本文件）— 系统当前能力状态
3. `../2026-06-04_S09_intel_radar_design.md` — 完整设计规范

"""
    (skills_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    print(f"  [skill_evolver] SKILL.md 已更新（{week_label}）")
