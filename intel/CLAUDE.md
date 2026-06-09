# CLAUDE.md — CIOSH 情报雷达项目

> 本文件是所有进入 `ciosh/intel/` 的 Agent 的强制约束文件。
> 执行任何子任务前必须先读取本文件，再读取 `skills/SKILL.md` 了解系统当前能力状态。

---

## 项目快速上下文

CIOSH 情报雷达是一个**零服务依赖的本地 Python 脚本系统**，用于每日自动采集 EHS / 工业安全 / 新型 PPE 品类情报，并通过四层 Skill 进化机制持续提升分析能力，支撑杜塞尔多夫展览（上海）CIOSH 劳保展的品类扩张工作（目标年度 2027）。

**三层架构：**
- **采集层**：Tavily（国际）+ 百度新闻 + 知乎 + B站（国内），全量关键词搜索，无 URL seed 信源，无任何手动录入通道（抖音/小红书不在系统内）
- **处理层**：三层漏斗（URL 去重 → 标题评分 → DeepSeek 分析），Layer3 采用**分桶限额**：Tavily ≤ 15 条 / 国内通道 ≤ 25 条，每日总量 ≤ 40 条
- **Skill 进化层**：四轮进化（词库 / 过滤规则 / Analyzer Prompt / 品类简报），全部与周报同频执行

**Cron 时间（UTC）：**
- 日报：`0 19 * * *` = 北京时间每天 03:00
- 周报：`30 19 * * 0` = 北京时间每周一 03:30

**关键文件导航：**
```
skills/SKILL.md                ← 系统当前能力状态（每周自动更新，进入必读）
skills/analyzer_prompt/        ← 版本化分析 Prompt（人工确认后更新）
skills/layer2_rules/           ← 版本化过滤权重（自动更新）
skills/category_briefs/        ← 各品类情报简报（每周追加，每月浓缩）
keyword_db.json                ← 活的关键词库
data/ciosh_intel.db            ← SQLite 数据库（唯一数据写入途径）
services/role_reporter.py      ← 三角色邮件生成（销售/市场/展会运营）
```

**完整设计规范：** `../docs/2026-06-04_S10_intel_radar_design.md`（含 Skill 层完整设计，Section 14）

---

## 硬性约束（不可违反）

### 0. 每次回答必须以 "Hello Max" 开头

无论任何场景，任何输出的第一行必须是 `Hello Max`。

### 1. Think Before Coding — 编前先想，不藏困惑

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- 明确陈述你的假设。不确定时，提问。
- 如果存在多种解读，列出来，不要自己悄悄选一个。
- 如果有更简单的方案，说出来。有异议时推回去。
- 如果有任何不清楚的地方，停下来，说明困惑点，提问。

### 2. Simplicity First — 最小代码原则

**Minimum code that solves the problem. Nothing speculative.**

- 不实现超出请求范围的功能。
- 单次使用的代码不做抽象封装。
- 没有被要求的"灵活性"或"可配置性"不写。
- 如果你写了 200 行但可以是 50 行，重写。

### 3. Surgical Changes — 外科手术式改动

**Touch only what you must. Clean up only your own mess.**

- 不"顺手优化"周边代码、注释或格式。
- 不重构没有损坏的东西。
- 发现无关的死代码时，提及它，不要删除它。
- 你的改动造成孤儿代码时，删除它们；但不删除原本就存在的死代码。

### 4. Goal-Driven Execution — 目标驱动执行

**Define success criteria. Loop until verified.**

多步骤任务，先陈述简要计划：
```
1. [步骤] → 验证：[检查方式]
2. [步骤] → 验证：[检查方式]
```

---

## 项目专属约束

### Token 纪律
- Layer3 采用分桶限额：Tavily 桶 `LAYER3_CAP_TAVILY`（默认15）/ 国内桶 `LAYER3_CAP_DOMESTIC`（默认25）
- 各桶内按 `layer2_score` 降序竞争，保证中英文信号均衡进入分析
- 只传标题 + snippet 给 AI，不抓取全文
- 报告生成以结构化拼接为主，AI 只做 ≤100 字导言

### Skill 层规则
- `analyzer.py` 的 System Prompt 从 `skills/analyzer_prompt/` 最新版本读取，不硬编码
- `layer2_filter.py` 的评分权重从 `skills/layer2_rules/` 最新版本读取，不硬编码
- `skills/category_briefs/` 内容只追加，不覆盖历史（月度浓缩除外）
- `skills/SKILL.md` 由 `weekly_job.py` 自动覆写，不手动编辑
- 邮件发单封统一日报，收件人由 `MAIL_TO`（主）+ `MAIL_CC`（抄送）控制，无角色分发字段

### 文件修改规则
- `keyword_db.json` 的任何修改必须同步更新 `last_updated` 和 `version` 字段
- `.env` 文件永远不写入代码仓库
- `data/ciosh_intel.db` 不手动编辑，只通过代码写入
- 禁止任何手动录入数据的接口或通道，唯一例外是直接操作 SQLite

### 项目文件命名规范（继承自 `../document_rules.md`）
- S-document：`docs/YYYY-MM-DD_S[N]_[topic_en].md`，S 编号连续不跳号
- Branding：`Branding/CIOSH_[descriptor].[ext]`，只用英文
- 归档：`archive/[category]/[name]`
- 本子项目（intel/）内部命名自行管理，不适用 S 编号

### 与 Geckos 的边界
- 不依赖 Geckos 的数据库、Flask 上下文或任何运行时状态
- 可复用 Geckos 代码逻辑，但必须复制到本项目，不做跨项目 import

---

*CIOSH Intel Radar · CLAUDE.md v1.2 · 2026-06-05*
