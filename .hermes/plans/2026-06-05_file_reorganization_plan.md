# CIOSH 项目文件重组方案

> 分析日期：2026-06-05
> 范围：`/Volumes/databoard/AI Project/ciosh/`（含 `intel/` 子项目）
> 原则：不改动任何文件，仅提出整改方案

---

## 0. 总体诊断

项目有两大独立子系统：

| 系统 | 位置 | 性质 |
|------|------|------|
| CIOSH 主项目（战略分析 + Demo + 品牌） | `ciosh/` 根目录 | BD 总监驱动，文档密集型 |
| Intel Radar（情报采集脚本） | `ciosh/intel/` | 技术系统，代码密集型 |

两者已有明确的边界感（各自有 `Agent.md` / `CLAUDE.md`），但主项目的根目录已开始堆积 Intel 无法归类的东西，需要规范化。

---

## 1. 可归档文件（移到 archive/ 保持不删）

这些文件已经完成历史使命（任务已交付、截图已分析、脚本已跑完），但保留有追溯价值。

### 1.1 intel/ 内的 MISSION 文件（4 个）

| 文件 | 说明 | 建议 |
|------|------|------|
| `intel/MISSION_PHASE2TO6.md` | Phase 2-6 任务书（452行） | → `intel/archive/missions/` |
| `intel/MISSION_PHASE7.md` | Phase 7 任务书（345行） | → `intel/archive/missions/` |
| `intel/MISSION_PHASE7_RESULT.md` | Phase 7 执行结果 | → `intel/archive/missions/` |
| `intel/MISSION_RESULT.md` | Phase 5 执行结果（命名不一致） | → `intel/archive/missions/` |

理由：任务已完成，但保留可追溯。`MISSION_RESULT.md` 实际是 Phase 5 的结果，命名缺少 Phase 编号。

### 1.2 一次性 Python 脚本（3 个）

| 文件 | 说明 | 建议 |
|------|------|------|
| `add_slides.py` | PPT 幻灯片追加脚本 | → `archive/scripts/` |
| `build_ppt.py` | PPT 构建脚本 | → `archive/scripts/` |
| `download_ciosh_data.py` | 数据下载脚本（已产物化） | → `archive/scripts/` |

理由：这些脚本不会再次运行，保留供参考。

### 1.3 screenshots/ 目录（3 张截图）

| 文件 | 来源 | 建议 |
|------|------|------|
| `screenshots/mod1_ExJoinInfo.png` | S03 展商后台分析 | → `archive/screenshots/2026-04-28_S03/` |
| `screenshots/step1_home.png` | S03 展商后台分析 | → `archive/screenshots/2026-04-28_S03/` |
| `screenshots/step3_exhibitorInfo.png` | S03 展商后台分析 | → `archive/screenshots/2026-04-28_S03/` |

理由：关联 S03 文档，归档到对应 S 编号下而非散落根目录。

### 1.4 .hermes/plans/ 内部计划（3 个）

| 文件 | 说明 | 建议 |
|------|------|------|
| `.hermes/plans/2026-05-07_1747-branding-file-tools-research.md` | 品牌文件工具调研 | 不动（Hermes 内部存储） |
| `.hermes/plans/2026-05-08_155000-miniapp-portal-research-and-checkin-plan.md` | 小程序签到调研 | 不动 |
| `.hermes/plans/2026-05-09_154500-h5-microofficialsite-vs-miniapp-analysis.md` | H5 vs 小程序分析 | 不动 |

理由：这是 Hermes Agent 自己的工作产物，属于 `.hermes/` 命名空间，与项目文件无关。**不需要处理**。

### 1.5 .claude/CLAUDE.md（过期副本）

| 文件 | 说明 | 建议 |
|------|------|------|
| `.claude/CLAUDE.md` | intel/CLAUDE.md 的 v1.0 旧版 | → 删除（见第2节） |

理由：`intel/CLAUDE.md` 已是 v1.1 权威版本，`.claude/` 下的 v1.0 副本会造成混淆。

---

## 2. 可清理文件（直接删除）

这些文件无保留价值，删除不会丢失任何信息。

| 文件 | 理由 |
|------|------|
| `.DS_Store`（根目录） | macOS 系统垃圾 |
| `intel/.DS_Store` | macOS 系统垃圾 |
| `intel/skills/.DS_Store` | macOS 系统垃圾 |
| `.hermes/.DS_Store` | macOS 系统垃圾 |
| `intel/__pycache__/`（含 cpython-312 和 cpython-310） | Python 缓存，两个版本混存说明环境切换过 |
| `intel/services/__pycache__/` | Python 缓存 |
| `intel/scripts/__pycache__/` | Python 缓存 |
| `intel/data/test.txt` | 测试残留，内容大概率是调试用临时文件 |
| `.claude/CLAUDE.md` | 与 `intel/CLAUDE.md` 重复的旧版（v1.0 vs v1.1），保留 intel/ 下的 |

> 注：`.gitignore` 已覆盖 `__pycache__/` 和 `*.pyc`，清理后不会再次进入 git 追踪。

---

## 3. 命名规范整改

### 3.1 核心问题：S 编号冲突

当前 S-document 命名规范（`document_rules.md` 定义）：

```
YYYY-MM-DD_S[N]_[主题简述].md
```

实际文件清单：

| 文件 | S 编号 | 日期 | 问题 |
|------|--------|------|------|
| `2026-04-24_S01_品类断层图谱.md` | S01 | 04-24 | ✅ |
| — | S02 | — | ❌ 缺失 |
| `2026-04-28_S03_poc_transformation_plan.md` | S03 | 04-28 | ✅ |
| `2026-04-30_S04_laobao_cloud_audit_and_miniapp_feasibility.md` | S04 | 04-30 | ✅ |
| `2026-04-30_S05_expocloud_audit_and_dual_saas_comparison.md` | S05 | 04-30 | ⚠️ 同日 S04+S05+S06 |
| `2026-04-30_S06_exhibitor_query_page_analysis.md` | S06 | 04-30 | ✅ |
| `2026-05-07_S05_internal_interview_and_transformation_feasibility.md` | **S05（重复！）** | 05-07 | ❌ S05 已用 |
| `2026-05-09_190000-ciosh-demo-prototype.md` | **无 S 编号** | 05-09 | ❌ 格式异常 |
| `2026-05-09_S07_demand_scoping_labor_gloves.md` | S07 | 05-09 | ✅ |
| `2026-05-09_S08_sommelier_bot_competitive_analysis.md` | S08 | 05-09 | ✅ |
| `2026-06-04_S09_intel_radar_design.md` | S09 | 06-04 | ✅ |

**两个错误需修正：**

#### 错误 1：S05 重复
```
2026-04-30_S05_expocloud_audit_and_dual_saas_comparison.md    ← 真正的 S05
2026-05-07_S05_internal_interview_and_transformation_feasibility.md ← 应为 S06，但 S06 已被 04-30 占用
```

**建议方案：**
- 保留 04-30 的 S04/S05/S06 不动（同日产出，合理）
- 将 05-07 的文件重编号为 **S07**（原 S07→S08, 原 S08→S09, 原 S09→S10）

这样调整后：
```
S01: 04-24  品类断层图谱
S02: （空缺 — 确认是否真的缺失）
S03: 04-28  PoC 转型计划
S04: 04-30  劳保云审计+小程序可行性
S05: 04-30  Expocloud 审计+双SaaS对比
S06: 04-30  展商查询页分析
S07: 05-07  内部访谈与转型可行性  ← 修正
S08: 05-09  劳保手套需求摸排        ← 顺延
S09: 05-09  Sommelier Bot 竞品分析  ← 顺延
S10: 06-04  Intel Radar 设计        ← 顺延
```

#### 错误 2：缺少 S 编号
```
2026-05-09_190000-ciosh-demo-prototype.md
```
应改为 `2026-05-09_S08_ciosh_demo_prototype.md`（如按上述调整则为 S09）。

### 3.2 命名风格不统一

| 问题 | 示例 | 建议 |
|------|------|------|
| 中文主题用下划线连接 | `品类断层图谱` | ✅ 保持 |
| 英文主题混用 hyphen/underscore | `h5-microofficialsite-vs-miniapp-analysis` | 统一用 underscore：`h5_vs_miniapp_analysis` |
| 带时间戳无 S 编号 | `190000-ciosh-demo-prototype` | 去掉时间戳，加 S 编号 |
| Branding 文件中文名 | `劳保会IP吉祥物 转曲.ai` | 保留中文名但建议加英文别名 README |

### 3.3 统一命名规则（提案）

```
# 战略分析文档
YYYY-MM-DD_S[N]_[英文简述用_underscore].md

# 允许中文主题但必须小写英文 slug 并存
2026-04-24_S01_category_gap_map_品类断层图谱.md

# 数据导出
[YYYY-MM-DD]_[内容描述].[csv|xlsx]

# 一次性脚本
archive/scripts/[日期或用途]_[名称].py

# 截图
archive/screenshots/YYYY-MM-DD_S[N]/[stepN_description].png
```

---

## 4. 目录结构重整方案（目标状态）

```
ciosh/
├── Agent.md                          # 项目身份卡（不动）
├── README.md                         # 项目说明（不动）
├── document_rules.md                 # 命名规范（不动）
│
├── docs/                             # 新建：战略分析文档集中
│   ├── S01_2026-04-24_category_gap_map_品类断层图谱.md
│   ├── S03_2026-04-28_poc_transformation_plan.md
│   ├── S04_2026-04-30_laobao_cloud_audit.md
│   ├── S05_2026-04-30_expocloud_audit.md
│   ├── S06_2026-04-30_exhibitor_query_page_analysis.md
│   ├── S07_2026-05-07_internal_interview.md
│   ├── S08_2026-05-09_demand_scoping_labor_gloves.md
│   ├── S09_2026-05-09_sommelier_bot_competitive_analysis.md
│   ├── S10_2026-06-04_intel_radar_design.md
│   └── S09_demo_2026-05-09_ciosh_demo_prototype.md
│
├── data/                             # 新建：结构化数据集中
│   ├── ciosh_data.db                 # ← 从根目录移入
│   └── CIOSH2026展商名单.xlsx        # ← 从根目录移入
│
├── exports/                          # 重命名：csv_export_for_excel →
│   ├── README_给同事看这个.txt
│   ├── exhibitors.csv
│   ├── exhibition_base.csv
│   ├── forecast_exhibitors.csv
│   ├── journals.csv
│   ├── org_unit_stats.csv
│   └── 重点_参展届数校验表.csv
│
├── Branding/                         # 不动
│   ├── README.md                     # 建议新增：品牌文件索引
│   ├── logo_header.png
│   ├── kv_header.png
│   ├── header_1200.png
│   ├── CIOSH-1966.ai
│   ├── CIOSH 2026 SH KV 横版加60_0121.eps
│   ├── CIOSH 2026 SH KV 竖版加60_0121.eps
│   ├── In partnership with A+A.ai
│   └── 劳保会IP吉祥物 转曲.ai
│
├── ciosh-demo/                       # 不动
│   ├── index.html
│   ├── exhibitor.html
│   └── env.js
│
├── as_is_manual_file/                # 不动
│   ├── CIOSH 2026 申请表.pdf
│   ├── CIOSH预登记字段.xlsx
│   ├── ciosh_exhibitor_group.xlsx
│   ├── 第110届中国国际劳动保护用品交易会--观众数据报告.pdf
│   └── 第110届劳保会1355-天津市宝坻区祥容手套厂-展位合同.pdf
│
├── output/                           # 不动（未来产出放这里）
│   └── CIOSH_Blackbox_拆解路径.pptx
│
├── intel/                            # 子项目（独立边界）
│   ├── CLAUDE.md                     # 权威版本 v1.1
│   ├── config.py
│   ├── models.py
│   ├── requirements.txt
│   ├── keyword_db.json
│   ├── .env
│   ├── .gitignore
│   ├── data/
│   │   └── ciosh_intel.db
│   ├── scripts/
│   │   ├── daily_job.py
│   │   ├── weekly_job.py
│   │   ├── seed_job.py
│   │   ├── run_daily.sh
│   │   ├── run_weekly.sh
│   │   └── setup_cron.sh
│   ├── services/
│   │   ├── analyzer.py
│   │   ├── domestic_searcher.py
│   │   ├── keyword_evolver.py
│   │   ├── layer2_filter.py
│   │   ├── mailer.py
│   │   ├── reporter.py
│   │   ├── searcher.py
│   │   └── skill_evolver.py
│   ├── skills/
│   │   ├── SKILL.md
│   │   ├── analyzer_prompt/
│   │   │   ├── v1.md
│   │   │   └── proposals/
│   │   ├── layer2_rules/
│   │   │   └── v1.json
│   │   └── category_briefs/
│   │       ├── ehs_tech.md
│   │       ├── emergency_response.md
│   │       ├── env_monitoring.md
│   │       ├── fire_safety.md
│   │       ├── industrial_safety.md
│   │       ├── policy_regulatory.md
│   │       └── smart_ppe.md
│   ├── tests/
│   │   └── test_phase2.py
│   └── archive/
│       └── missions/
│           ├── MISSION_PHASE2TO6.md
│           ├── MISSION_PHASE7.md
│           ├── MISSION_PHASE7_RESULT.md
│           └── MISSION_RESULT.md       # 建议改名为 MISSION_PHASE5_RESULT.md
│
├── archive/                          # 新建：主项目归档
│   ├── scripts/
│   │   ├── add_slides.py
│   │   ├── build_ppt.py
│   │   └── download_ciosh_data.py
│   └── screenshots/
│       └── 2026-04-28_S03/
│           ├── mod1_ExJoinInfo.png
│           ├── step1_home.png
│           └── step3_exhibitorInfo.png
│
└── .hermes/                          # 不动（Hermes 内部）
    └── plans/
        ├── 2026-05-07_1747-branding-file-tools-research.md
        ├── 2026-05-08_155000-miniapp-portal-research-and-checkin-plan.md
        └── 2026-05-09_154500-h5-microofficialsite-vs-miniapp-analysis.md
```

---

## 5. 执行优先级

| 优先级 | 操作 | 影响范围 | 风险 |
|--------|------|----------|------|
| P0 🔴 | 删除 `.DS_Store` × 4 | 无 | 无 |
| P0 🔴 | 删除 `__pycache__/` × 3 | 无 | 无 |
| P0 🔴 | 删除 `.claude/CLAUDE.md` | 无 | 确认 intel/CLAUDE.md 是最新的 |
| P1 🟡 | 修正 S05 重复编号 | 3 个文件重命名 | 需更新 intel/CLAUDE.md 中的引用路径 `../2026-06-04_S09_...` |
| P1 🟡 | 修正无 S 编号的 demo 文档 | 1 个文件重命名 | 需检查是否有文档引用它 |
| P2 🟢 | 移动 S-documents → docs/ | 10 个文件 | 需更新 README.md 中的路径引用 |
| P2 🟢 | 移动数据文件 → data/ | 2 个文件 | 需检查 `download_ciosh_data.py` 是否引用 `ciosh_data.db` |
| P2 🟢 | 重命名 csv_export_for_excel → exports/ | 目录重命名 | 需通知同事 README 路径变更 |
| P3 🔵 | 归档 MISSION 文件 | 4 个文件 | 无 |
| P3 🔵 | 归档一次性脚本 | 3 个文件 | 确认无 cron 引用 |
| P3 🔵 | 归档旧截图 | 3 个文件 | 无 |

---

## 6. 待确认事项（需 Max 决策）

1. **S02 确实缺失？** 是跳过了还是文件丢失？
2. **S 编号方案选择**：
   - 方案 A：按上述调整重排（S05 冲突修正，后续顺延）— 影响 3 个文件名
   - 方案 B：保持现状不动 S 编号，仅归档和清理 — 零影响但混乱持续
3. **docs/ 集中化**：是否接受把所有 S-document 从根目录移入 `docs/`？根目录会清爽很多。
4. **Branding 中文命名**：是否需要加英文别名？如 `mascot.ai` → 实际文件 `劳保会IP吉祥物 转曲.ai`。
5. **csv_export_for_excel → exports**：目录改名后是否要通知已拿到 README 的同事？

---

*本方案不修改任何文件，待 Max 确认后分步执行。*
