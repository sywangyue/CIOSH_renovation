![CIOSH 2026 KV](Branding/header_1200.png)

# CIOSH 劳保展 · 第二曲线项目

> 中国国际劳动保护用品交易会（CIOSH）数字化转型与战略陪跑项目。
> 主色：<span style="color:#009748">█ #009748</span> 绿 · <span style="color:#f39700">█ #f39700</span> 橙

---

## 项目背景

CIOSH 是中国最大的 PPE（个人防护装备）展会，由**杜塞尔多夫展览（上海）有限公司（MDS）**与中国纺织品商业协会合资运营。

项目当前处于稳定/瓶颈期，核心问题：**展商品类过度单一**，全部集中在低级别 PPE 产品（手套/劳保服/防护面具/面料），需要"第二曲线"为展会创造新的落脚点与架构。

目标年度：**2027** 拓展出新的业务体（新展区 / 新展商 / 新展团 / 新观众）。

## 仓库内容

| 目录/文件 | 说明 |
|---|---|
| `Agent.md` | 项目身份卡，所有 Agent 进入项目的必读文件 |
| `document_rules.md` | 文件命名规范 |
| `docs/` | S-document 战略分析文档（S01-S10） |
| `Branding/` | CIOSH 品牌视觉文件（AI/EPS/PNG，英文命名） |
| `ciosh-demo/` | CIOSH 品类渗透引擎 Demo 原型 |
| `as_is_manual_file/` | 现场原始文件（Excel/PDF 合同/数据报告） |
| `data/` | 结构化数据文件（数据库/展商名单） |
| `output/` | 分析报告与 PPT 产出 |
| `archive/` | 历史归档（一次性脚本/过期截图） |
| `intel/` | 情报雷达子项目（独立 Python 脚本系统，详见下方） |

---

## 情报雷达（intel/）

每日自动采集 EHS / 工业安全 / 新型 PPE 品类情报，通过 AI 分析后发送 HTML 邮件日报，支撑品类扩张的数据侧决策。

### 系统架构

```
采集层  →  处理层（三层漏斗）  →  Skill 进化层
```

**采集层**（双通道）
- **Tavily**：国际英文内容，覆盖 EHS tech / smart PPE / occupational health 等
- **百度新闻**：国内中文内容，覆盖 EHS 管理 / 智能安全帽 / 工业物联网安全等

**处理层（三层漏斗）**

| 层 | 逻辑 | 限额 |
|---|---|---|
| Layer 1 | URL 去重（simhash 指纹，85 相似度阈值） | — |
| Layer 2 | 标题关键词评分过滤 | 通过 score ≥ 1 |
| Layer 3 | DeepSeek AI 深度分析 | Tavily ≤ 15 条 / 国内 ≤ 25 条 / 日总量 ≤ 40 条 |

**Skill 进化层**（每周一 03:30 自动运行）
- 关键词库进化（词频 + 情报密度驱动）
- Layer 2 过滤权重进化
- Analyzer Prompt 版本管理（人工确认后生效）
- 品类简报更新（只追加，不覆盖）

### 运行时间

| 任务 | 时间 | 触发方式 |
|---|---|---|
| 日报 | 每天 03:00 北京时间 | macOS LaunchAgent |
| 周报 + Skill 进化 | 每周一 03:30 北京时间 | macOS LaunchAgent |

### 关键词库

当前共 **31 个关键词**，分三级：

- **Tier 1**（19 个，每日必跑）：核心 EHS / PPE / 安全监测品类
- **Tier 2**（6 个，每日必跑）：国际英文关键词
- **Tier 3**（6 个，仅周一运行）：新兴/扩展品类

### 品类体系

| 品类标签 | 覆盖方向 |
|---|---|
| `ehs_tech` | EHS 数字化、智能安全帽、可穿戴设备 |
| `industrial_safety` | 工厂安全生产、机器人安全、矿山设备 |
| `policy_regulatory` | 安全标准、职业健康政策、合规动态 |
| `smart_ppe` | 新型 PPE、IoT 传感器、VR 培训 |
| `other` | 品类外但有参考价值的信号 |

### 文件结构

```
intel/
├── scripts/
│   ├── daily_job.py          # 日报主流程
│   └── weekly_job.py         # 周报 + Skill 进化主流程
├── services/
│   ├── domestic_searcher.py  # 百度/知乎/B站 搜索通道
│   ├── searcher.py           # Tavily 搜索通道
│   ├── layer2_filter.py      # Layer2 标题评分（权重从 skills/ 读取）
│   ├── analyzer.py           # Layer3 DeepSeek 分析（Prompt 从 skills/ 读取）
│   ├── reporter.py           # HTML 邮件日报生成
│   └── mailer.py             # SMTP 发送（163邮箱）
├── skills/
│   ├── SKILL.md              # 系统当前能力状态（每周自动覆写）
│   ├── analyzer_prompt/      # 版本化分析 Prompt
│   ├── layer2_rules/         # 版本化过滤权重
│   └── category_briefs/      # 各品类情报简报
├── data/ciosh_intel.db       # SQLite 数据库（唯一写入途径）
├── keyword_db.json           # 活的关键词库
├── config.py                 # 配置（从 .env 读取）
└── CLAUDE.md                 # Agent 硬性约束文件
```

### 依赖与配置

**外部服务**：Tavily API（国际搜索）· DeepSeek API（AI 分析）· 163 SMTP（邮件发送）

**必填环境变量**（`.env`，不入库）：
```
TAVILY_API_KEY=
DEEPSEEK_API_KEY=
SMTP_USER=
SMTP_PASSWORD=
MAIL_TO=
MAIL_CC=        # 抄送，逗号分隔，可为空
```

**安装**：
```bash
cd intel
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 当前运行状态

> 数据截至 2026-W24（自动更新，见 `intel/skills/SKILL.md`）

- 累计情报条目：47 条
- URL 指纹库：506 条
- Analyzer Prompt：v1.md（v2 待审核）

---

## 转型目标

- **新展区**：突破单一 PPE 品类
- **新展商**：从自媒体信号中捕获采购需求，反向匹配展商
- **新展团**：建立跨品类展商联盟
- **新观众**：结构性增加，而非数量堆叠

## 推进方式

- 节奏：1 年长期陪跑
- 方法：数字化转型 + 战略陪跑
- 打法：逐个点位击破，不做大而全的方案

---

*MDS Shanghai · BD 总监 Max · 2026*
