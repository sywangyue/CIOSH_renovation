"""
CIOSH 情报雷达 · 角色摘要 + 统一 HTML 报告（日报/周报共用）
synthesize_role_digests: 单次 DeepSeek 调用，生成三角色 bullet-point 摘要
build_unified_html: 一封邮件，Header / A-角色摘要 / B-高优先级 / B-中优先级 / C-其他情报 / D-关键词健康与退休词
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
LIGHT_GREEN  = "#e8f5e9"
LIGHT_ORANGE = "#fff3e0"
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


# ─── 角色摘要合成（单次 DeepSeek 调用）────────────────────────────────────────

def synthesize_role_digests(items: list[dict[str, Any]]) -> dict[str, str]:
    """
    对当日/本周 high+medium 条目做一次 DeepSeek 调用，生成三角色 bullet-point 摘要。
    items < 3 或 API 失败时返回三个空字符串，不中断主流程。
    """
    _EMPTY = {"sales_digest": "", "market_digest": "", "ops_digest": ""}

    relevant = [i for i in items if (i.get("priority") or "").lower() in ("high", "medium")]
    if len(relevant) < 3:
        return _EMPTY

    item_lines = "\n".join(
        f"- [{i.get('category','?')}] {i.get('title','')}：{i.get('summary_zh','')}"
        for i in relevant[:30]
    )

    system_prompt = (
        "你是CIOSH情报雷达的报告合成器。基于当日情报，为三个角色各生成一段≤150字的中文摘要。\n"
        "每段摘要必须用多行bullet points格式（每条以\"• \"开头），禁止段落文字。\n"
        "销售：聚焦哪些具体品类/行业有展商机会，以及对应的销售切入点。\n"
        "市场：聚焦行业市场价值、趋势数据、可用于客户沟通的市场话术。\n"
        "运营：聚焦论坛主题方向、新品类与现有展会结构的整合建议。"
    )
    user_prompt = (
        f"今日情报（共 {len(relevant)} 条高/中优先级）：\n{item_lines}\n\n"
        "请严格按以下 JSON 格式输出，不要输出其他内容：\n"
        '{\n'
        '  "sales_digest": "• 第一条\\n• 第二条\\n• 第三条",\n'
        '  "market_digest": "• 第一条\\n• 第二条",\n'
        '  "ops_digest": "• 第一条\\n• 第二条"\n'
        '}'
    )

    try:
        from services.analyzer import _call_deepseek, _parse_json_from_text
        raw = _call_deepseek(system_prompt, user_prompt)
        parsed = _parse_json_from_text(raw)
        return {
            "sales_digest":  str(parsed.get("sales_digest",  "") or ""),
            "market_digest": str(parsed.get("market_digest", "") or ""),
            "ops_digest":    str(parsed.get("ops_digest",    "") or ""),
        }
    except Exception as e:
        print(f"  [role_reporter] synthesize_role_digests 失败 — {e}")
        return _EMPTY


# ─── HTML 组件 ─────────────────────────────────────────────────────────────────

def _safe_url(url: str) -> str:
    return url if (url or "").startswith(("http://", "https://")) else "#"


def _section_label(text: str) -> str:
    return (
        f'<div style="font-size:13px;color:{MUTED};letter-spacing:0.08em;'
        f'text-transform:uppercase;margin-bottom:12px;font-family:{FONT};">{text}</div>'
    )


def _bullet_block(text: str) -> str:
    """将 '• 行1\n• 行2' 转为 HTML 行块；文本为空时显示占位提示。"""
    if not text or not text.strip():
        return f'<div style="color:{MUTED};font-size:12px;">今日数据不足，暂无摘要</div>'
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    rows = "".join(
        f'<div style="font-size:12px;color:{DARK};line-height:1.6;'
        f'margin-bottom:2px;font-family:{FONT};">{_html.escape(ln)}</div>'
        for ln in lines
    )
    return rows


def _role_card(title: str, digest: str, accent: str) -> str:
    return (
        f'<div style="margin-bottom:8px;border-left:3px solid {accent};padding-left:10px;">'
        f'<div style="font-size:11px;font-weight:bold;color:{DARK};'
        f'margin-bottom:8px;font-family:{FONT};">{title}</div>'
        f'{_bullet_block(digest)}'
        f'</div>'
    )


def _priority_badge(priority: str) -> str:
    color = GREEN if priority == "high" else ORANGE
    label = "HIGH" if priority == "high" else "MED"
    return (
        f'<span style="background:{color};color:{WHITE};font-size:11px;'
        f'font-weight:bold;padding:2px 7px;border-radius:3px;'
        f'font-family:{FONT};">{label}</span>'
    )


def _category_tag(category: str) -> str:
    label = _CATEGORY_NAMES.get(category, category)
    return (
        f'<span style="font-size:12px;color:{GREEN};background:#e8f5e9;'
        f'padding:1px 6px;border-radius:3px;font-family:{FONT};">{label}</span>'
    )


def _item_row_b(item: dict[str, Any], seq_num: int, is_last: bool) -> str:
    category = item.get("category") or "other"
    summary = _html.escape(item.get("summary_zh") or "")
    url = _safe_url(item.get("url") or "")
    border = "" if is_last else f"border-bottom:1px dashed {BORDER};"
    seq_span = f'<span style="font-size:11px;color:{MUTED};font-family:{FONT};">▸&nbsp;{seq_num:02d}&nbsp;</span>'
    summary_link = (
        f'<a href="{url}" style="color:{DARK};text-decoration:underline;'
        f'font-family:{FONT};">{summary}</a>'
    )
    return (
        f'<div style="padding:6px 0;{border}">'
        f'<div style="margin-bottom:4px;">{seq_span}{_category_tag(category)}</div>'
        f'<div style="font-size:14px;color:{DARK};line-height:1.6;font-family:{FONT};">{summary_link}</div>'
        f'</div>'
    )


def _item_row_c(item: dict[str, Any], seq_num: int) -> str:
    url = _safe_url(item.get("url") or "")
    title = _html.escape(item.get("title") or "")
    category = item.get("category") or "other"
    cat_label = _CATEGORY_NAMES.get(category, category)
    seq_span = f'<span style="font-size:11px;color:{MUTED};font-family:{FONT};">▸&nbsp;{seq_num:02d}&nbsp;</span>'
    return (
        f'<div style="padding:4px 0;font-size:10px;font-family:{FONT};">'
        f'{seq_span}<a href="{url}" style="color:{GREEN};text-decoration:none;">{title}</a>'
        f'&nbsp;<span style="color:{MUTED};font-size:10px;">[{cat_label}]</span>'
        f'</div>'
    )


def _priority_block(
    items: list[dict[str, Any]],
    border_color: str,
    bg_color: str,
    seq_start: int,
) -> tuple[str, int]:
    """
    Wraps items in a left-border colored block for Part B.
    Returns (html_str, next_seq_num).
    If items is empty, returns ("", seq_start) — no wrapper div rendered.
    """
    if not items:
        return ("", seq_start)
    rows = []
    for i, item in enumerate(items):
        seq_num = seq_start + i
        is_last = (i == len(items) - 1)
        rows.append(_item_row_b(item, seq_num, is_last))
    block = (
        f'<div style="border-left:4px solid {border_color};'
        f'background:{bg_color};padding:4px 12px;margin-bottom:12px;">'
        + "".join(rows)
        + f'</div>'
    )
    return (block, seq_start + len(items))


def _divider() -> str:
    return f'<div style="border-top:1px solid {BORDER};margin:20px 0;"></div>'


def _keyword_section(
    kw_health_data: dict[str, dict],
    retired: list[str],
    new_candidates: list[str],
) -> str:
    sorted_kws = sorted(kw_health_data.items(), key=lambda x: x[1]["yield_rate"], reverse=True)
    kw_rows = ""
    for word, s in sorted_kws[:20]:
        rate = s.get("yield_rate", 0.0)
        bar_color = GREEN if rate >= 0.2 else (ORANGE if rate >= 0.05 else MUTED)
        bar_w = min(int(rate * 400), 120)
        kw_rows += (
            f'<tr style="border-bottom:1px solid {BORDER};">'
            f'<td style="padding:5px 8px;font-size:13px;font-family:{FONT};">{_html.escape(word)}</td>'
            f'<td style="padding:5px 8px;font-size:13px;text-align:right;">{s.get("total", 0)}</td>'
            f'<td style="padding:5px 8px;font-size:13px;text-align:right;">{s.get("quality", 0)}</td>'
            f'<td style="padding:5px 8px;">'
            f'<div style="display:inline-block;width:{bar_w}px;height:10px;'
            f'background:{bar_color};vertical-align:middle;border-radius:2px;"></div>'
            f'&nbsp;<span style="font-size:12px;color:{DARK};">{rate:.1%}</span>'
            f'</td></tr>'
        )
    kw_table = (
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<tr style="background:{GRAY_BG};">'
        f'<th style="padding:6px 8px;text-align:left;font-size:12px;">关键词</th>'
        f'<th style="padding:6px 8px;text-align:right;font-size:12px;">总命中</th>'
        f'<th style="padding:6px 8px;text-align:right;font-size:12px;">高质量</th>'
        f'<th style="padding:6px 8px;text-align:left;font-size:12px;">产出率</th>'
        f'</tr>{kw_rows}</table>'
    ) if sorted_kws else f'<p style="color:{MUTED};font-size:13px;">暂无数据</p>'

    retired_html = ""
    if retired:
        tags = "".join(
            f'<span style="display:inline-block;margin:3px;padding:4px 10px;'
            f'background:{GRAY_BG};color:{MUTED};border-radius:3px;font-size:13px;'
            f'text-decoration:line-through;font-family:{FONT};">{_html.escape(w)}</span>'
            for w in retired
        )
        retired_html = (
            f'<div style="margin-top:16px;">'
            + _section_label("退休词")
            + f'<div>{tags}</div></div>'
        )

    new_html = ""
    if new_candidates:
        tags = "".join(
            f'<span style="display:inline-block;margin:3px;padding:4px 10px;'
            f'border:1px solid {GREEN};border-radius:3px;font-size:13px;'
            f'color:{GREEN};font-family:{FONT};">{_html.escape(w)}</span>'
            for w in new_candidates
        )
        new_html = (
            f'<div style="margin-top:16px;">'
            + _section_label("新词提案")
            + f'<div>{tags}</div>'
            f'<p style="font-size:12px;color:{MUTED};margin-top:8px;font-family:{FONT};">'
            f'如需升为 Tier1/2，请直接编辑 keyword_db.json 修改 tier 字段。</p>'
            f'</div>'
        )

    return kw_table + retired_html + new_html


# ─── 统一报告 HTML（日报/周报共用）──────────────────────────────────────────────

def build_unified_html(
    items: list[dict[str, Any]],
    role_digests: dict[str, str],
    date_or_week_label: str,
    kw_health_data: dict[str, dict] | None = None,
    retired: list[str] | None = None,
    new_candidates: list[str] | None = None,
    report_kind: str = "daily",
) -> str:
    """
    统一日报/周报构建函数。
    report_kind="daily"  → 日报，D 区块展示当日关键词命中快照
    report_kind="weekly" → 周报，D 区块展示本周完整健康报告+退休词/新词提案
    """
    total = len(items)
    high_items = [i for i in items if (i.get("priority") or "").lower() == "high"]
    med_items  = [i for i in items if (i.get("priority") or "").lower() == "medium"]
    low_items  = [i for i in items if (i.get("priority") or "").lower() == "low"]

    # ── Header ────────────────────────────────────────────────────────────────
    kind_label = "日报" if report_kind == "daily" else "周报"
    header = (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="background:{GREEN};">'
        f'<tr>'
        f'<td style="padding:16px 20px;">'
        f'<span style="color:{WHITE};font-size:18px;font-weight:bold;'
        f'font-family:{FONT};">CIOSH 情报雷达</span>'
        f'</td>'
        f'<td style="padding:16px 20px;text-align:right;">'
        f'<span style="color:{WHITE};font-size:13px;opacity:0.9;'
        f'font-family:{FONT};">{date_or_week_label}&nbsp;·&nbsp;{kind_label}&nbsp;·&nbsp;{total}条</span>'
        f'</td>'
        f'</tr>'
        f'</table>'
    )

    # ── Part A：角色摘要 ──────────────────────────────────────────────────────
    part_a = (
        f'<div style="padding:20px 20px 0 20px;">'
        + _section_label("A &nbsp; 角色摘要")
        + _role_card("销售视角", role_digests.get("sales_digest", ""), GREEN)
        + _role_card("市场视角", role_digests.get("market_digest", ""), ORANGE)
        + _role_card("运营视角", role_digests.get("ops_digest", ""), GREEN)
        + f'</div>'
    )

    # ── Part B：优先级分组色块 ─────────────────────────────────────────────────
    high_sorted = sorted(high_items, key=lambda x: x.get("source_keyword") or "")
    med_sorted  = sorted(med_items,  key=lambda x: x.get("source_keyword") or "")

    b_green_html,  seq_after_high = _priority_block(high_sorted, GREEN,  LIGHT_GREEN,  1)
    b_orange_html, seq_after_med  = _priority_block(med_sorted,  ORANGE, LIGHT_ORANGE, seq_after_high)
    b_gray_html,   seq_after_b    = _priority_block(low_items,   MUTED,  GRAY_BG,      seq_after_med)

    part_b = (
        f'<div style="padding:0 20px;">'
        + _divider()
        + _section_label("B &nbsp; 重点情报")
        + b_green_html
        + b_orange_html
        + b_gray_html
        + f'</div>'
    )

    # ── Part C：其他情报 ──────────────────────────────────────────────────────
    # NOTE: low_items are now also shown in Part B gray block.
    # Part C shows "unknown" priority items not captured by high/med/low filters.
    unknown_items = [
        i for i in items
        if (i.get("priority") or "").lower() not in ("high", "medium", "low")
    ]
    if unknown_items:
        c_rows = "".join(
            _item_row_c(item, seq_after_b + idx)
            for idx, item in enumerate(unknown_items)
        )
        part_c_body = c_rows
    else:
        part_c_body = (
            f'<div style="color:{MUTED};font-size:13px;padding:8px 0;">'
            f'今日无其他情报</div>'
        )

    part_c = (
        f'<div style="padding:0 20px;">'
        + _divider()
        + _section_label("C &nbsp; 其他情报")
        + part_c_body
        + f'</div>'
    )

    # ── Part D：关键词健康与退休词 ────────────────────────────────────────────
    if kw_health_data:
        d_content = _keyword_section(
            kw_health_data,
            retired or [],
            new_candidates or [],
        )
        part_d = (
            f'<div style="padding:0 20px 20px 20px;">'
            + _divider()
            + _section_label("D &nbsp; 关键词健康与退休词")
            + d_content
            + f'</div>'
        )
    else:
        part_d = f'<div style="padding:0 20px 20px 20px;"></div>'

    # ── Footer ────────────────────────────────────────────────────────────────
    footer = (
        f'<div style="background:{GRAY_BG};border-top:1px solid {BORDER};'
        f'padding:12px 20px;text-align:center;">'
        f'<span style="font-size:12px;color:{MUTED};font-family:{FONT};">'
        f'CIOSH 情报雷达 · 自动生成</span>'
        f'</div>'
    )

    return (
        f'<!DOCTYPE html><html lang="zh-CN">'
        f'<head><meta charset="utf-8"/>'
        f'<title>CIOSH情报{kind_label} {date_or_week_label}</title></head>'
        f'<body style="margin:0;padding:0;background:{GRAY_BG};">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        f' style="background:{GRAY_BG};padding:20px 0;">'
        f'<tr><td align="center">'
        f'<table width="620" cellpadding="0" cellspacing="0" border="0"'
        f' style="background:{WHITE};border-radius:4px;overflow:hidden;max-width:620px;">'
        f'<tr><td>{header}</td></tr>'
        f'<tr><td>{part_a}</td></tr>'
        f'<tr><td>{part_b}</td></tr>'
        f'<tr><td>{part_c}</td></tr>'
        f'<tr><td>{part_d}</td></tr>'
        f'<tr><td>{footer}</td></tr>'
        f'</table>'
        f'</td></tr></table>'
        f'</body></html>'
    )
