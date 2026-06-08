# CIOSH Intel Radar — Execution Mission: Phase 8

> **Executor:** Claude Code
> **Reviewer:** Cowork Claude（完成后二次校验）
> **Pre-read required:** `CLAUDE.md` + `skills/SKILL.md` + `../docs/2026-06-04_S10_intel_radar_design.md`（v1.3，重点看 §3 架构图、§5.1/5.3/5.4/5.6、附录A、Token 表）
> **This is Phase 8：** 国内通道收缩（停用知乎/B站，架构保留）+ 定时任务流程一致性审计 + 时间戳语义审计 + 统一邮件版式重排（A/B/C/D 四段式，日报周报共用同一模板）
> **Working directory：** 所有文件在 `ciosh/intel/` 内，除非特别说明
> **Pre-condition：** Phase 7 已完成；此前两个小修复（crontab 自动写入 / 周报配色对齐日报）已验证完成，本任务在此基础上继续

---

## Before You Start

```bash
cd /path/to/AI\ Project/ciosh/intel

# 确认上一轮两个小修复已生效
crontab -l | grep "CIOSH Intel Radar"      # 应能看到两行 cron 配置
python -c "
import sqlite3
conn = sqlite3.connect('data/ciosh_intel.db')
row = conn.execute(\"SELECT html_body FROM reports WHERE report_type='weekly' ORDER BY id DESC LIMIT 1\").fetchone()
bad = ['#B0C4DE', '#FFA000', '#FFF8E1', '#546E7A', '#C62828', '#E65100']
print('周报仍含非品牌色：', [c for c in bad if c in row[0]] or '无（已对齐）')
"
```

若以上任一项未生效，先停下汇报，不要继续 Phase 8。

---

## Task 8-A：停用知乎 / B站通道（架构与代码骨架完整保留）

**背景：** 实测知乎、B站抓取内容的可信度（标题相关性、信息质量）显著低于百度新闻，且反爬限制更严格。决定停用这两个通道，但**不删除任何代码**——保留 `search_zhihu` / `search_bilibili` 函数体、`source_channel` 枚举值、数据库 schema、依赖包，未来评估后可随时重新启用。

在 `services/domestic_searcher.py` 中：

```python
def search_all_domestic(
    word: str, date_range_days: int = 1, max_results_each: int = 5
) -> list[dict]:
    """
    顺序调用国内通道并合并结果，任一失败不影响其他。

    停用说明（2026-06-08）：知乎 / B站可信度评估不达标，已从调用链移除。
    search_zhihu / search_bilibili 函数体保留在本模块内，可单独调用验证；
    若未来重新启用，只需把它们加回下面的 fn 元组即可，无需重写。
    """
    results = []
    for fn in (search_baidu,):   # 原为 (search_baidu, search_zhihu, search_bilibili)
        results.extend(fn(word, date_range_days=date_range_days, max_results=max_results_each))
        time.sleep(1)
    return results
```

- 只改 `search_all_domestic` 的调用元组和函数文档字符串，`search_baidu` / `search_zhihu` / `search_bilibili` 三个函数体本身一字不动
- 不删除 `bilibili_api` import（仍在 `search_bilibili` 内使用），不动 `requirements.txt`

**验证：**
```bash
python -c "
import sys; sys.path.insert(0, '.')
from services.domestic_searcher import search_all_domestic, search_zhihu, search_bilibili
r = search_all_domestic('EHS管理', max_results_each=2)
channels = set(i.get('source_channel') for i in r)
print('search_all_domestic 返回的通道：', channels)   # 期望：仅 {'baidu'}
print('search_zhihu 函数仍可独立调用：', callable(search_zhihu))
print('search_bilibili 函数仍可独立调用：', callable(search_bilibili))
"
```

---

## Task 8-B：定时任务流程一致性审计（以核查为主，发现不一致才做最小修复）

**背景：** 设计已最终定稿为唯一路径：

```
cron（crontab，UTC触发）→ python daily_job.py / weekly_job.py（脚本内跑完全部步骤）→ 163 SMTP 直接发送
```

不存在邮件触发、IMAP 轮询或任何中间环节。请逐一核对以下文件中的描述/注释/print 文本，确认全部与这条唯一路径一致：

- `scripts/daily_job.py`、`scripts/weekly_job.py`（docstring、print 输出）
- `scripts/run_daily.sh`、`scripts/run_weekly.sh`（注释）
- `scripts/setup_cron.sh`（输出文案）
- `../docs/2026-06-04_S10_intel_radar_design.md` §3 架构图、§5.1（已在 v1.3 中补充"流程定稿声明"）、§5.3/§5.4 流程图

若发现任何残留的"邮件触发""IMAP 轮询""模式 B"等措辞或与此路径矛盾的描述，做文本级最小修正即可（不改变任何运行逻辑、不改变文件结构）。若全部一致，直接在执行报告里写明"核查通过，无需改动"。

---

## Task 8-C：时间戳语义审计（以核查为主，发现实现与文档不符时以代码为准更新文档）

**背景：** S10 v1.3 已明确：日报采用"过去24小时滚动窗口 ≈ 前一天"语义，周报采用"过去7天滚动窗口 ≈ 上一周"语义——这是**设计意图**（情报系统要最新内容而非严格日历切割），不是 bug，不需要改成日历切割。请核对实现是否与该语义匹配：

- `services/searcher.py::search_keyword`：`client.search(topic="news", days=days_back, ...)`，`days_back` 默认 1
- `services/domestic_searcher.py::search_baidu`：URL 中 `tbs=qdr:d`（百度"一天内"过滤）
- `services/domestic_searcher.py::search_zhihu` / `search_bilibili`（虽已停用，仍检查其 `cutoff` 计算逻辑是否自洽，便于未来重新启用）
- `scripts/daily_job.py::main`：`report_date = (datetime.now() - timedelta(days=1))`，传给搜索函数的 `days_back=1` / `date_range_days=1`
- `scripts/weekly_job.py` → `services/keyword_evolver.py::compute_weekly_stats(conn, days=7)`：SQL 中 `collected_at >= date('now', '-7 days')`

**核查标准：** 以上实现只要保持"滚动 N 天窗口"语义、且 N 与文档描述（日报1天/周报7天）一致，即视为通过，**不需要改动代码**。如果发现某处 N 值或窗口语义与文档描述不符（例如某处用了固定日历日期比较），以代码实际行为为准，回到 §10 在 S10 文档中做对应文本修正（不改代码逻辑，除非确认是明显错误）。

---

## Task 8-D：统一邮件版式重排（A/B/C/D 四段式，日报周报共用一套模板）

**背景：** 配色不变（仍是 CIOSH 品牌色 GREEN `#009040` / ORANGE `#f39700` / DARK `#221b19` / WHITE `#ffffff` / GRAY_BG `#f5f5f5` / BORDER `#e0e0e0` / MUTED `#999999`），**只调整排版结构**。新版式整体由 6 个部分自上而下组成：Header / A-角色摘要 / B-高优先级情报 / B-中优先级情报 / C-其他情报 / D-关键词健康与退休词。

### 改动点 1 — Part A 角色摘要：三列并排 → 三行纵排

`services/role_reporter.py::build_unified_html` 当前用 `<table><tr>` 把销售/市场/运营三张卡片横排（`_role_card` 里 `width:33%`）。改为纵向堆叠三行：

- 去掉外层 `<table><tr>`，改成三个 `_role_card` 依次 `<div>` 纵向排列，每行之间留 `margin-bottom:12px`
- 每行内部结构不变（左侧色条 + 标题 + bullet 列表）
- 字号在现有基础上调小 2px：标题从 13px → 11px，bullet 文本从 14px → 12px

### 改动点 2 — Part B 拆分为"高优先级"/"中优先级"两个独立区块

当前 `_item_row_b` 把 high+medium 混在一个列表里。改为：

- 先用 `[i for i in items if priority=='high']` 渲染一个区块（小标题"B · 高优先级情报（N条）"）
- 再用 `[i for i in items if priority=='medium']` 渲染另一个区块（小标题"中优先级情报（N条）"），紧跟在高优先级区块下方
- 任一优先级为空时显示"暂无"占位文案（参考现有 `_section_label` + 占位逻辑）

### 改动点 3 — Part B 条目链接方式：摘要本身变为带下划线超链接

当前 `_item_row_b` 把摘要做成纯文本，下面单独一行"→ 查看原文"链接。改为：

```python
def _item_row_b(item, is_last):
    ...
    summary = item.get("summary_zh") or ""
    url = item.get("url") or "#"
    # 摘要文字本身包一层 <a>，加下划线，去掉单独的"查看原文"行
    summary_link = (
        f'<a href="{url}" style="color:{DARK};text-decoration:underline;'
        f'font-family:{FONT};">{summary}</a>'
    )
    return (
        f'<div style="padding:12px 0;{border}">'
        f'<div style="margin-bottom:6px;">{_priority_badge(priority)}&nbsp;&nbsp;{_category_tag(category)}</div>'
        f'<div style="font-size:14px;color:{DARK};line-height:1.6;font-family:{FONT};">{summary_link}</div>'
        f'</div>'
    )
```

不再渲染"→ 查看原文"那一行（删除对应代码，属于本次改动产生的孤儿代码，按规则清理）。

### 改动点 4 — Part C 字号调整

`_item_row_c` 当前 14px。在 B 区块字号基础上调小 4px → 10px。链接样式保持现状（标题做超链接，不加下划线，颜色用 `{GREEN}`），不要和 B 区块的下划线风格混淆。

### 改动点 5 — 新增 Part D：关键词健康与退休词合并区块

参考 `services/reporter.py` 中既有的 `关键词健康报告` 实现（`kw_table` 构建逻辑：按 `yield_rate` 降序排列、进度条着色规则），原样移植到 `role_reporter.py`，只做品牌色对齐（把 `GREEN`/`ORANGE`/`MUTED`/`DARK`/`BORDER`/`GRAY_BG` 换成本文件已定义的常量），不改变信息结构。再把"退休词 / 新词提案"标签列表拼在同一个 `_section` 区块内，作为 D 区块的下半部分（参考 `reporter.py::build_weekly_html` 中"新词提案"的 `<span>` 标签样式，同样做品牌色对齐）。

- **日报场景**：D 区块展示"当日"关键词命中快照（可复用 `daily_job.py` 里已经统计出的 `results_by_kw` / `quality_by_kw`，按命中数排序展示 Top 10~15 即可，不需要额外查询）
- **周报场景**：D 区块展示"本周"完整健康报告（`compute_weekly_stats` 全量结果）+ 本周退休词 + 新词提案

### 改动点 6 — 日报周报合并为同一套构建函数

把 `build_unified_html` 改造成可同时服务日报和周报的统一函数（建议签名形如 `build_unified_html(items, role_digests, date_or_week_label, kw_health_data, retired, new_candidates, report_kind="daily"|"weekly")`，具体参数形态你来定，原则是"一套结构、两种数据源"）：

- `daily_job.py` 调用它，传入"当日" items + 当日关键词命中快照
- `weekly_job.py` 改为调用它（不再用 `services/reporter.py::build_weekly_html`），传入"本周" high_items + `compute_weekly_stats` 结果 + retired + new_candidates
- `services/reporter.py::build_weekly_html` 及其专属辅助函数变为孤儿代码：**提示但不要删除**（按 CLAUDE.md 规则，你的改动造成的孤儿代码要清理，但 `reporter.py` 整个模块在改动前就存在且仍可能被其他地方引用，先确认无引用后再决定是否连同模块一起清理，并在执行报告中说明判断依据）

---

## 禁止事项（硬性）

- 不引入本任务未描述的任何功能或灵活性
- 不修改任何颜色常量（GREEN/ORANGE/DARK/WHITE/GRAY_BG/BORDER/MUTED 保持不变，本次只改排版）
- 不删除 `search_zhihu` / `search_bilibili` 函数体及 `bilibili-api-python` 依赖
- 不改变 `cron → daily_job.py/weekly_job.py → 163 SMTP` 这条唯一运行路径
- 不把 Layer3 分桶限额、Skill 进化等已定稿逻辑卷入本次改动范围

---

## 验证清单

```
[ ] search_all_domestic('EHS管理') 只返回 source_channel='baidu' 的结果
[ ] search_zhihu / search_bilibili 仍可独立导入并调用（架构保留确认）
[ ] daily_job.py 跑完后生成的邮件 HTML 内可见 6 个区块：Header/A/B-高/B-中/C/D，且 A 为纵向三行
[ ] B 区块每条情报的摘要文字本身是带下划线的可点击链接，且没有单独的"查看原文"行
[ ] C 区块字号比 B 区块小 4px，链接样式与此前一致（无下划线）
[ ] D 区块同时展示关键词健康表 + 退休词/新词提案，配色为 CIOSH 品牌色
[ ] weekly_job.py 生成的周报与日报共用同一套区块结构（数据来源不同，排版一致）
[ ] grep 邮件 HTML，确认无任何非品牌色 hex 值
[ ] crontab 中两条任务仍正常（未受本次改动影响）
```

完成后在 `MISSION_PHASE8_RESULT.md` 中汇报：每个 Task 的改动文件 + 关键 diff 摘要 + 验证清单逐项结果。
