# CIOSH Intel Radar — Phase 8 Mission Result

> 执行时间：2026-06-08
> 执行人：Claude Code
> 验证人：Cowork Claude（待二次校验）

---

## 前置条件核查

| 项目 | 结果 | 说明 |
|---|---|---|
| crontab 两条任务 | ✅ | `0 19 * * *` 和 `30 19 * * 0` 均在位 |
| 周报配色对齐 | ⚠️ 代码已修复，DB 快照未刷新 | reporter.py 品牌色已修复，但今日 04:25 cron 在修复前已生成周报（幂等保护，下周一才会刷新）；Phase 8 Task 8-D 完全替换了周报构建器，此快照不再相关 |

---

## Task 8-A：停用知乎 / B站通道

**改动文件：** `services/domestic_searcher.py`

**变更：**
- `search_all_domestic` 调用元组从 `(search_baidu, search_zhihu, search_bilibili)` 改为 `(search_baidu,)`
- 更新函数 docstring，注明停用说明（2026-06-08）及重新启用方式
- `search_baidu` / `search_zhihu` / `search_bilibili` 三个函数体**一字未动**
- `bilibili_api` import、`requirements.txt` 均未改动

**附带修正：** `scripts/daily_job.py` Step 2 注释由"国内三通道"更新为"百度新闻"（因 8-A 导致描述不准确）

**验证结果：**
```
search_all_domestic 返回的通道：{'baidu'}   ✅ 仅 baidu
search_zhihu 函数仍可独立调用：True         ✅ 架构保留
search_bilibili 函数仍可独立调用：True       ✅ 架构保留
```

---

## Task 8-B：定时任务流程一致性审计

**核查结论：核查通过，无需改动。**

| 文件 | 核查结果 |
|---|---|
| `scripts/daily_job.py` | 无 IMAP/邮件触发措辞，Step 8 明确"163 SMTP 发送" ✅ |
| `scripts/weekly_job.py` | Step 6 标注"发送邮件"，无模式 B 残留 ✅ |
| `scripts/run_daily.sh` | 仅日志包装，无流程描述冲突 ✅ |
| `scripts/run_weekly.sh` | 仅日志包装，无流程描述冲突 ✅ |
| `scripts/setup_cron.sh` | 仅写入 crontab，无 IMAP 措辞 ✅ |
| `docs/2026-06-04_S10_intel_radar_design.md` | §5.1 v1.3 已有"流程定稿声明"，§3 架构图已对齐 ✅ |

---

## Task 8-C：时间戳语义审计

**核查结论：核查通过，实现与文档语义一致，无需改动。**

| 位置 | 实现 | 文档语义 | 结果 |
|---|---|---|---|
| `searcher.py::search_keyword` | `client.search(days=days_back)` | 滚动 N 天窗口 | ✅ |
| `domestic_searcher.py::search_baidu` | `tbs=qdr:d`（百度"一天内"） | 过去24小时滚动 | ✅ |
| `domestic_searcher.py::search_zhihu` | `cutoff = now - timedelta(days=range+1)` | 滚动窗口，自洽 | ✅ |
| `domestic_searcher.py::search_bilibili` | 同上 `cutoff_ts` | 滚动窗口，自洽 | ✅ |
| `daily_job.py::main` | `timedelta(days=1)`，`days_back=1`，`date_range_days=1` | 过去24小时 ≈ 前一天 | ✅ |
| `keyword_evolver.py::compute_weekly_stats` | `since = timedelta(days=7)`，`WHERE collected_at >= ?` | 滚动7天窗口 | ✅ |

---

## Task 8-D：统一邮件版式重排

**改动文件：** `services/role_reporter.py`（全面重写）、`scripts/daily_job.py`（调用更新）、`scripts/weekly_job.py`（构建器切换）

### 改动点 1 — Part A 角色摘要：三列并排 → 三行纵排

- `_role_card` 从 `<td>` 改为 `<div>`，`margin-bottom:12px` 纵向堆叠
- 标题字号：13px → **11px**
- Bullet 文本字号：14px → **12px**（在 `_bullet_block` 中更新）
- Part A 中去掉外层 `<table><tr>`，三个 `_role_card` 依次纵排

### 改动点 2 — Part B 拆分为两个独立区块

- 高优先级区块：小标题"高优先级情报（N条）"
- 中优先级区块：小标题"中优先级情报（N条）"
- 任一优先级为空时显示"暂无"占位文案

### 改动点 3 — Part B 条目：摘要本身变为带下划线超链接

- `_item_row_b`：摘要包一层 `<a href style="text-decoration:underline">`
- 删除原"→ 查看原文"行（属本次改动产生的孤儿代码，已清理）

### 改动点 4 — Part C 字号：14px → 10px

- `_item_row_c`：`font-size:14px` 改为 `font-size:10px`
- 链接样式不变（无下划线，颜色 `{GREEN}`）

### 改动点 5 — Part D：关键词健康与退休词合并区块（新增）

- 新增 `_keyword_section(kw_health_data, retired, new_candidates)` 函数
- 品牌色对齐（移植自 `reporter.py::build_weekly_html`，替换所有颜色常量）
- 关键词健康表（yield_rate 降序，进度条着色规则与 reporter.py 一致）
- 退休词标签列表
- 新词提案标签列表（带"如需升为 Tier1/2"说明）

### 改动点 6 — 日报周报合并为同一套构建函数

`build_unified_html` 新签名：
```python
def build_unified_html(
    items, role_digests, date_or_week_label,
    kw_health_data=None, retired=None, new_candidates=None,
    report_kind="daily"
)
```

**daily_job.py 更新：**
- 在 Step 6.5 后计算 `kw_health_data`（从 `results_by_kw`/`quality_by_kw` Top 15）
- `build_unified_html` 调用传入 `kw_health_data`、空 `retired=[]`、空 `new_candidates=[]`

**weekly_job.py 更新：**
- 导入从 `services.reporter` 改为 `services.role_reporter`
- 查询扩展为全优先级（不再只取 high），LIMIT 100
- 新增 `synthesize_role_digests(all_items)` 调用
- `build_unified_html` 传入 `kw_health_data=stats`、`retired`、`new_candidates`、`report_kind="weekly"`

---

## 孤儿代码说明

`services/reporter.py` 中的 `build_weekly_html` 和 `build_daily_html` 均已无外部调用引用：
- `build_weekly_html`：本次 weekly_job.py 切换造成的孤儿
- `build_daily_html`：Phase 7 daily_job.py 切换造成的孤儿（已存在于本次改动前）

**决策：保留 `reporter.py` 文件，不删除。** 理由：`reporter.py` 整个模块在改动前就存在，按 CLAUDE.md 规则"发现无关的死代码时，提及它，不要删除它"。如需清理，建议单独提一个 cleanup 任务。

---

## 验证清单

```
[x] search_all_domestic('EHS管理') 只返回 source_channel='baidu' 的结果
[x] search_zhihu / search_bilibili 仍可独立导入并调用（架构保留确认）
[x] build_unified_html 生成 HTML 含 6 个区块：Header/A/B-高/B-中/C/D
[x] A 为纵向三行（无 <table><tr> 包裹角色卡，验证通过）
[x] B 区块每条情报的摘要文字本身是带下划线可点击链接
[x] B 区块没有单独的"查看原文"行
[x] C 区块字号 10px（B 区块 14px 基础上减 4px）
[x] D 区块同时展示关键词健康表 + 退休词/新词提案，配色为 CIOSH 品牌色
[x] weekly_job.py 生成的周报与日报共用同一套区块结构（report_kind 参数区分）
[x] grep HTML，无非品牌色 hex 值（#B0C4DE/#FFA000/#FFF8E1/#546E7A/#C62828/#E65100 均未出现）
[x] crontab 中两条任务仍正常（未受本次改动影响）
```

---

## 待人工操作

- [ ] 下次 `daily_job.py` 运行后，确认收到统一邮件（含 A/B-高/B-中/C/D 六段）
- [ ] 下次 `weekly_job.py` 运行后，确认收到周报（与日报结构一致）
- [ ] 确认是否需要独立 cleanup 任务清理 `reporter.py`

---

*CIOSH Intel Radar · Phase 8 Result · 2026-06-08*
*Pending secondary verification by Cowork Claude*
