"""
CIOSH 情报雷达 · HTML 日报生成
纯模板拼接，0 token。
"""

import html as _html
import sys
from pathlib import Path
from typing import Any

_INTEL_DIR = Path(__file__).resolve().parent.parent
if str(_INTEL_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEL_DIR))

# ─── CIOSH 品牌色（严格使用，不得替换）─────────────────────────────────────────
GREEN   = "#009040"
ORANGE  = "#f39700"
DARK    = "#221b19"
WHITE   = "#ffffff"
GRAY_BG = "#f5f5f5"
BORDER  = "#e0e0e0"
MUTED   = "#999999"
FONT    = ("'Helvetica Neue',Helvetica,'PingFang SC',"
           "'Hiragino Sans GB','Microsoft YaHei',Arial,sans-serif")

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
    "high":   GREEN,
    "medium": ORANGE,
    "low":    MUTED,
}

_PRIORITY_LABELS: dict[str, str] = {
    "high":   "高",
    "medium": "中",
    "low":    "低",
}

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _safe_url(url: str) -> str:
    return url if (url or "").startswith(("http://", "https://")) else "#"


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:3px;'
        f'background:{color};color:{WHITE};font-size:11px;font-weight:bold;">{text}</span>'
    )


def _item_card(item: dict[str, Any], compact: bool = False) -> str:
    title = _html.escape(item.get("title") or "")
    url = _safe_url(item.get("url") or "")
    summary = _html.escape(item.get("summary_zh") or "")
    action = _html.escape(item.get("ciosh_action") or "")
    category = item.get("category") or "other"
    priority = (item.get("priority") or "low").lower()
    source_kw = _html.escape(item.get("source_keyword") or "")

    cat_label = _CATEGORY_NAMES.get(category, category)
    pri_color = _PRIORITY_COLORS.get(priority, MUTED)
    pri_label = _PRIORITY_LABELS.get(priority, priority)

    badges = (
        _badge(cat_label, GREEN) + "&nbsp;" +
        _badge(f"优先级：{pri_label}", pri_color)
    )

    title_html = f'<a href="{url}" style="color:{GREEN};font-weight:bold;text-decoration:none;">{title}</a>'

    if compact:
        return (
            f'<tr><td style="padding:8px 0;border-bottom:1px solid {BORDER};">'
            f'{title_html}<br/>'
            f'<span style="color:{DARK};font-size:13px;">{summary}</span>&nbsp;&nbsp;{badges}'
            f'</td></tr>'
        )

    action_html = ""
    if action:
        action_html = (
            f'<div style="margin-top:8px;padding:8px 12px;background:{GRAY_BG};'
            f'border-left:3px solid {ORANGE};font-size:13px;color:{DARK};">'
            f'<strong>CIOSH 建议：</strong>{action}</div>'
        )

    source_html = (
        f'<div style="margin-top:6px;font-size:11px;color:{MUTED};">'
        f'来源关键词：{source_kw}</div>'
    ) if source_kw else ""

    return (
        f'<div style="background:{WHITE};border:1px solid {BORDER};border-radius:4px;'
        f'padding:14px 16px;margin-bottom:12px;">'
        f'<div style="margin-bottom:6px;">{badges}</div>'
        f'<div style="font-size:15px;margin-bottom:6px;">{title_html}</div>'
        f'<div style="font-size:13px;color:{DARK};line-height:1.6;">{summary}</div>'
        f'{action_html}{source_html}'
        f'</div>'
    )


def _section(title: str, color: str, rows_html: str) -> str:
    return (
        f'<div style="margin-bottom:20px;">'
        f'<div style="background:{color};color:{WHITE};padding:8px 14px;'
        f'font-weight:bold;border-radius:3px 3px 0 0;font-size:14px;">{title}</div>'
        f'<div style="background:{GRAY_BG};padding:12px 14px;border:1px solid {BORDER};'
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
        sections_html += _section(f"高优先级情报（{len(high)}条）", GREEN, rows)

    if medium:
        rows = "".join(_item_card(i) for i in medium)
        sections_html += _section(f"中优先级情报（{len(medium)}条）", ORANGE, rows)

    if low:
        rows = '<table style="width:100%;border-collapse:collapse;">' + \
               "".join(_item_card(i, compact=True) for i in low) + \
               '</table>'
        sections_html += _section(f"低优先级（{len(low)}条）", MUTED, rows)

    if not items:
        sections_html = f'<p style="color:{MUTED};text-align:center;padding:20px;">今日无新增情报</p>'

    stats_html = (
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;color:{DARK};">'
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
<body style="margin:0;padding:0;background:{GRAY_BG};font-family:{FONT};">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{GRAY_BG};padding:20px 0;">
  <tr><td align="center">
    <table width="620" cellpadding="0" cellspacing="0" border="0"
           style="background:{WHITE};border-radius:4px;overflow:hidden;max-width:620px;">

      <!-- 标题栏 -->
      <tr><td style="background:{GREEN};padding:18px 24px;">
        <div style="color:{WHITE};font-size:20px;font-weight:bold;">CIOSH 品类情报雷达</div>
        <div style="color:{WHITE};opacity:0.8;font-size:13px;margin-top:4px;">
          情报覆盖日期：{report_date} &nbsp;|&nbsp; 新增 {len(items)} 条
        </div>
      </td></tr>

      <!-- 漏斗统计 -->
      <tr><td style="background:{GRAY_BG};border-bottom:1px solid {BORDER};padding:4px 0;">
        {stats_html}
      </td></tr>

      <!-- 情报内容 -->
      <tr><td style="padding:20px 20px 10px 20px;">
        {sections_html}
      </td></tr>

      <!-- 页脚 -->
      <tr><td style="background:{GRAY_BG};padding:12px 20px;text-align:center;
                     font-size:11px;color:{MUTED};border-top:1px solid {BORDER};">
        本邮件由 CIOSH 情报雷达自动生成 · 仅供内部参考
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


