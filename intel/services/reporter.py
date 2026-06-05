"""
CIOSH 情报雷达 · HTML 日报生成
纯模板拼接，0 token。
"""

import sys
from pathlib import Path
from typing import Any

_INTEL_DIR = Path(__file__).resolve().parent.parent
if str(_INTEL_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEL_DIR))

_CATEGORY_NAMES: dict[str, str] = {
    "core_ppe":          "传统PPE",
    "ehs_tech":          "EHS科技",
    "smart_ppe":         "智慧防护",
    "industrial_safety": "工业安全",
    "fire_safety":       "消防安全",
    "env_monitoring":    "环境监测",
    "emergency_response":"应急响应",
    "policy_regulatory": "政策法规",
    "market_signal":     "市场信号",
    "other":             "其他",
}

_PRIORITY_COLORS: dict[str, str] = {
    "high":   "#C62828",
    "medium": "#E65100",
    "low":    "#546E7A",
}

_PRIORITY_LABELS: dict[str, str] = {
    "high":   "高",
    "medium": "中",
    "low":    "低",
}

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:3px;'
        f'background:{color};color:#fff;font-size:11px;font-weight:bold;">{text}</span>'
    )


def _item_card(item: dict[str, Any], compact: bool = False) -> str:
    title = item.get("title") or ""
    url = item.get("url") or "#"
    summary = item.get("summary_zh") or ""
    action = item.get("ciosh_action") or ""
    category = item.get("category") or "other"
    priority = (item.get("priority") or "low").lower()
    source_kw = item.get("source_keyword") or ""

    cat_label = _CATEGORY_NAMES.get(category, category)
    pri_color = _PRIORITY_COLORS.get(priority, "#546E7A")
    pri_label = _PRIORITY_LABELS.get(priority, priority)

    badges = (
        _badge(cat_label, "#1B3A6B") + "&nbsp;" +
        _badge(f"优先级：{pri_label}", pri_color)
    )

    title_html = f'<a href="{url}" style="color:#1B3A6B;font-weight:bold;text-decoration:none;">{title}</a>'

    if compact:
        return (
            f'<tr><td style="padding:8px 0;border-bottom:1px solid #EEEEEE;">'
            f'{title_html}<br/>'
            f'<span style="color:#555;font-size:13px;">{summary}</span>&nbsp;&nbsp;{badges}'
            f'</td></tr>'
        )

    action_html = ""
    if action:
        action_html = (
            f'<div style="margin-top:8px;padding:8px 12px;background:#FFF8E1;'
            f'border-left:3px solid #FFA000;font-size:13px;color:#333;">'
            f'<strong>CIOSH 建议：</strong>{action}</div>'
        )

    source_html = (
        f'<div style="margin-top:6px;font-size:11px;color:#888;">'
        f'来源关键词：{source_kw}</div>'
    ) if source_kw else ""

    return (
        f'<div style="background:#fff;border:1px solid #E0E0E0;border-radius:4px;'
        f'padding:14px 16px;margin-bottom:12px;">'
        f'<div style="margin-bottom:6px;">{badges}</div>'
        f'<div style="font-size:15px;margin-bottom:6px;">{title_html}</div>'
        f'<div style="font-size:13px;color:#333;line-height:1.6;">{summary}</div>'
        f'{action_html}{source_html}'
        f'</div>'
    )


def _section(title: str, color: str, rows_html: str) -> str:
    return (
        f'<div style="margin-bottom:20px;">'
        f'<div style="background:{color};color:#fff;padding:8px 14px;'
        f'font-weight:bold;border-radius:3px 3px 0 0;font-size:14px;">{title}</div>'
        f'<div style="background:#FAFAFA;padding:12px 14px;border:1px solid #E0E0E0;'
        f'border-top:none;border-radius:0 0 3px 3px;">{rows_html}</div>'
        f'</div>'
    )


def build_daily_html(items: list[dict[str, Any]], stats: dict[str, int], report_date: str) -> str:
    """
    生成 HTML 日报。
    items: 已分析的情报条目（任意顺序，内部按优先级排序）
    stats: {keywords, raw, passed_layer2, analyzed}
    report_date: 情报覆盖日期（通常是昨天）
    """
    sorted_items = sorted(items, key=lambda x: _PRIORITY_ORDER.get((x.get("priority") or "low").lower(), 2))

    high = [i for i in sorted_items if (i.get("priority") or "").lower() == "high"]
    medium = [i for i in sorted_items if (i.get("priority") or "").lower() == "medium"]
    low = [i for i in sorted_items if (i.get("priority") or "").lower() == "low"]

    sections_html = ""

    if high:
        rows = "".join(_item_card(i) for i in high)
        sections_html += _section(f"高优先级情报（{len(high)}条）", "#C62828", rows)

    if medium:
        rows = "".join(_item_card(i) for i in medium)
        sections_html += _section(f"中优先级情报（{len(medium)}条）", "#E65100", rows)

    if low:
        rows = '<table style="width:100%;border-collapse:collapse;">' + \
               "".join(_item_card(i, compact=True) for i in low) + \
               '</table>'
        sections_html += _section(f"低优先级（{len(low)}条）", "#546E7A", rows)

    if not items:
        sections_html = '<p style="color:#888;text-align:center;padding:20px;">今日无新增情报</p>'

    stats_html = (
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;color:#555;">'
        f'<tr>'
        f'<td style="padding:6px 12px;text-align:center;">🔍 搜索词<br/><strong>{stats.get("keywords",0)}</strong></td>'
        f'<td style="padding:6px 12px;text-align:center;">📄 原始结果<br/><strong>{stats.get("raw",0)}</strong></td>'
        f'<td style="padding:6px 12px;text-align:center;">✅ 过漏斗<br/><strong>{stats.get("passed_layer2",0)}</strong></td>'
        f'<td style="padding:6px 12px;text-align:center;">🤖 AI分析<br/><strong>{stats.get("analyzed",0)}</strong></td>'
        f'</tr>'
        f'</table>'
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"/><title>CIOSH情报日报 {report_date}</title></head>
<body style="margin:0;padding:0;background:#F5F5F5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F5F5F5;padding:20px 0;">
  <tr><td align="center">
    <table width="620" cellpadding="0" cellspacing="0" border="0"
           style="background:#fff;border-radius:4px;overflow:hidden;max-width:620px;">

      <!-- 标题栏 -->
      <tr><td style="background:#1B3A6B;padding:18px 24px;">
        <div style="color:#fff;font-size:20px;font-weight:bold;">CIOSH 品类情报雷达</div>
        <div style="color:#B0C4DE;font-size:13px;margin-top:4px;">
          情报覆盖日期：{report_date} &nbsp;|&nbsp; 新增 {len(items)} 条
        </div>
      </td></tr>

      <!-- 漏斗统计 -->
      <tr><td style="background:#F0F4F8;border-bottom:1px solid #E0E0E0;padding:4px 0;">
        {stats_html}
      </td></tr>

      <!-- 情报内容 -->
      <tr><td style="padding:20px 20px 10px 20px;">
        {sections_html}
      </td></tr>

      <!-- 页脚 -->
      <tr><td style="background:#F5F5F5;padding:12px 20px;text-align:center;
                     font-size:11px;color:#999;border-top:1px solid #E0E0E0;">
        本邮件由 CIOSH 情报雷达自动生成 · 仅供内部参考
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def build_weekly_html(
    high_items: list[dict[str, Any]],
    keyword_stats: dict[str, dict],
    new_candidates: list[str],
    retired: list[str],
    week_label: str,
) -> str:
    """
    生成 HTML 周报。
    high_items: 本周 high 优先级情报
    keyword_stats: {word: {total, quality, yield_rate}}
    new_candidates: 待提案新词列表
    retired: 本周退休词列表
    week_label: 如 "2026-W23"
    """
    # ── 本周高优先级情报 ──────────────────────────────────────────────────────
    intel_html = ""
    if high_items:
        rows = "".join(_item_card(i) for i in high_items[:20])
        intel_html = _section(f"本周高优先级情报（{len(high_items)}条）", "#1B3A6B", rows)
    else:
        intel_html = '<p style="color:#888;text-align:center;padding:12px;">本周无高优先级情报</p>'

    # ── 关键词健康榜（按 yield_rate 降序）────────────────────────────────────
    sorted_kws = sorted(keyword_stats.items(), key=lambda x: x[1]["yield_rate"], reverse=True)
    kw_rows = ""
    for word, s in sorted_kws[:30]:
        rate = s["yield_rate"]
        bar_color = "#2E7D32" if rate >= 0.2 else ("#F57C00" if rate >= 0.05 else "#C62828")
        bar_w = min(int(rate * 400), 120)
        kw_rows += (
            f'<tr style="border-bottom:1px solid #eee;">'
            f'<td style="padding:5px 8px;font-size:13px;">{word}</td>'
            f'<td style="padding:5px 8px;font-size:13px;text-align:right;">{s["total"]}</td>'
            f'<td style="padding:5px 8px;font-size:13px;text-align:right;">{s["quality"]}</td>'
            f'<td style="padding:5px 8px;">'
            f'<div style="display:inline-block;width:{bar_w}px;height:10px;'
            f'background:{bar_color};vertical-align:middle;border-radius:2px;"></div>'
            f'&nbsp;<span style="font-size:12px;color:#555;">{rate:.1%}</span>'
            f'</td></tr>'
        )
    kw_table = (
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<tr style="background:#E8EAF6;">'
        f'<th style="padding:6px 8px;text-align:left;font-size:12px;">关键词</th>'
        f'<th style="padding:6px 8px;text-align:right;font-size:12px;">总命中</th>'
        f'<th style="padding:6px 8px;text-align:right;font-size:12px;">高质量</th>'
        f'<th style="padding:6px 8px;text-align:left;font-size:12px;">产出率</th>'
        f'</tr>{kw_rows}</table>'
    ) if sorted_kws else '<p style="color:#888;font-size:13px;">暂无数据</p>'
    health_section = _section("关键词健康报告", "#37474F", kw_table)

    # ── 新词提案 ───────────────────────────────────────────────────────────────
    proposal_html = ""
    if new_candidates:
        tags = "".join(
            f'<span style="display:inline-block;margin:3px;padding:4px 10px;'
            f'border:1px solid #1B3A6B;border-radius:3px;font-size:13px;color:#1B3A6B;">'
            f'{w}</span>'
            for w in new_candidates
        )
        proposal_html = _section(
            f"新词提案（{len(new_candidates)}个，已自动加入 Tier3）",
            "#2E7D32",
            f'<div>{tags}</div>'
            f'<p style="font-size:12px;color:#888;margin-top:8px;">'
            f'如需升为 Tier1/2，请直接编辑 keyword_db.json 修改 tier 字段。</p>',
        )

    # ── 退休词 ─────────────────────────────────────────────────────────────────
    retired_html = ""
    if retired:
        tags = "".join(
            f'<span style="display:inline-block;margin:3px;padding:4px 10px;'
            f'background:#ECEFF1;color:#546E7A;border-radius:3px;font-size:13px;'
            f'text-decoration:line-through;">{w}</span>'
            for w in retired
        )
        retired_html = _section(f"已退休词（{len(retired)}个）", "#546E7A", f'<div>{tags}</div>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"/><title>CIOSH情报周报 {week_label}</title></head>
<body style="margin:0;padding:0;background:#F5F5F5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F5F5F5;padding:20px 0;">
  <tr><td align="center">
    <table width="620" cellpadding="0" cellspacing="0" border="0"
           style="background:#fff;border-radius:4px;overflow:hidden;max-width:620px;">

      <tr><td style="background:#1B3A6B;padding:18px 24px;">
        <div style="color:#fff;font-size:20px;font-weight:bold;">CIOSH 品类情报雷达 · 周报</div>
        <div style="color:#B0C4DE;font-size:13px;margin-top:4px;">
          {week_label} &nbsp;|&nbsp; 高优先级 {len(high_items)} 条
        </div>
      </td></tr>

      <tr><td style="padding:20px 20px 10px 20px;">
        {intel_html}
        {health_section}
        {proposal_html}
        {retired_html}
      </td></tr>

      <tr><td style="background:#F5F5F5;padding:12px 20px;text-align:center;
                     font-size:11px;color:#999;border-top:1px solid #E0E0E0;">
        本邮件由 CIOSH 情报雷达自动生成 · 仅供内部参考
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""
