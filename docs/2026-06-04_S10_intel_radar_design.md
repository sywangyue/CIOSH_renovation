# CIOSH 品类情报雷达 · 系统设计规划书

> 文档编号：S09 · 版本：v1.3
> 日期：2026-06-04（v1.2 修订：2026-06-05 · v1.3 修订：2026-06-08）
> 作者：BD 总监 × Claude（Informa 顾问视角）
> 状态：**设计定稿，待执行**
>
> **v1.2 变更摘要：** 增加国内多通道搜索架构（百度新闻/知乎/B站）；移除 URL seed 信源层；明确禁止手动录入通道；修正 Bing API 引用错误；移除小红书/Playwright通道；增加多角色邮件架构；Layer3全量分析
>
> **v1.3 变更摘要：** 知乎/B站通道停用（架构与代码骨架保留，未来可重新启用，国内通道当前仅剩百度新闻）；固化定时任务流程为「cron → daily_job.py → 163 SMTP 直发」单一模式；明确日报/周报时间戳语义（日报=过去24小时滚动窗口≈前一日，周报=过去7天滚动窗口≈上一周）；统一邮件版式为 A/B/C/D 四段结构（角色摘要三行 / 高优先级与中优先级分两个区块 / 低优先级精简列表 / 关键词健康与退休词合并区块），日报周报共用同一模板

---

## 0. 前言：为什么要重新设计

Geckos 项目已经跑通了一套完整的情报流水线（采集 → 去重 → 分析 → 报告 → 邮件），但它的核心设计哲学是**"监控已知竞争对手的已知来源"**。这对 BD 总监的常规竞情监控够用，但对 CIOSH 品类扩张这个任务，是错误的工具。

CIOSH 的问题不是"缺情报"，而是**"不知道新品类的边界在哪里"**。这是一个探索性任务，需要的系统逻辑完全不同：


| 维度       | Geckos                | CIOSH 情报雷达                      |
| -------- | --------------------- | ------------------------------- |
| 核心驱动     | 已知数据源（URL/RSS）→ 拉取    | 关键词（热词库）→ 全网搜索                  |
| 目标       | 竞情监控（已知领域）            | 品类探索（未知边界）                      |
| 关键词库     | 静态，手动维护               | **动态自进化**，每周更新                  |
| AI 分析维度  | 通用展览行业（并购/新展/合作）      | **CIOSH 专属品类图谱**（EHS/智慧安全/新兴防护） |
| 系统依赖     | Flask Web App + 数据库   | **零服务依赖**，纯脚本 + SQLite          |
| Cron 触发  | 本地 cron → 直接执行 Python | 本地 cron → daily_job.py → 163 SMTP 直接发送（已定稿模式 A，见 §5.1）|
| Token 策略 | 无上限控制                 | **三层过滤漏斗**，AI 只看通过前两层的内容        |


本文档定义 CIOSH 情报雷达的完整系统设计。**Geckos 已有代码可复用的模块会明确标注，避免重复造轮子。**

---

## 1. 系统目标

**核心目标**：以最低 token 成本，每天自动发现与 CIOSH 品类扩张相关的增量信息，逐步建立 CIOSH 新品类机会图谱。

**具体可交付物**：

- 每日一封 163 邮件日报（HTML 格式），包含当日新增情报
- 每周一份关键词健康报告，含词库自动更新记录
- 本地 SQLite 数据库，持续积累情报历史
- 可随时查询的品类信号档案

---

## 2. 设计哲学（不可妥协的原则）

### 原则一：关键词优先，来源服从关键词

Geckos 是"先锁定来源，再从来源拉内容"。CIOSH 雷达是"先定关键词，再让关键词决定内容去哪找"。这个颠倒不是技术细节，是探索与监控两种不同认识论的体现。

### 原则二：三层漏斗，Token 只烧在第三层

```
全网搜索结果（原始标题 + URL）
       ↓ [第一层：URL 指纹去重，0 token]
  去掉重复 URL（已见过的）
       ↓ [第二层：标题关键词相关性评分，0 token]
  去掉与 CIOSH 品类无关的内容
       ↓ [第三层：DeepSeek 结构化分析，烧 token]
  进入数据库的高质量情报
```

原则：按来源通道分桶限额进入 Layer3，各桶内按 Layer2 分数排序取 Top N。
Tavily 桶上限：`LAYER3_CAP_TAVILY`（默认 15）
国内桶上限：`LAYER3_CAP_DOMESTIC`（默认 25，当前仅百度新闻参与竞争；知乎/B站通道已停用，架构预留，重新启用后将与百度合并竞争同一桶配额）
每日 Layer3 总量上限：≤ 40 条

### 原则三：关键词库是活的资产，不是配置文件

关键词库不是一次写好就不动的配置，它是系统学习的结晶。每周，系统从 AI 分析结果中提取高频出现的信号词，自动提案补充进词库；同时根据每个关键词的"有效产出率"淘汰低效词。**关键词库的质量 = 系统情报质量的天花板。**

### 原则四：零服务依赖，本地即全部

没有 Flask，没有 Web 服务器，没有 Redis，没有任何需要"保持运行"的进程。所有逻辑是 Python 脚本 + SQLite + cron，电脑睡眠时无影响，开机后 cron 补跑当天任务。

### 原则五：与 Geckos 是兄弟关系，不是父子关系

CIOSH 雷达复用 Geckos 的可复用代码（deduplicator、mailer、analyzer 底层 API 调用），但**不依赖 Geckos 的数据库、Flask 上下文、项目结构**。两个系统各自独立运行，互不干扰。

---

## 3. 系统架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                       本地 Mac（你的电脑）                         │
│                                                                   │
│  ┌─────────┐   ┌────────────────────────────────────────────┐    │
│  │  cron   │──▶│              daily_job.py                  │    │
│  │ 每天    │   │  1. 读取关键词库（全量热词）                 │    │
│  │ 03:00   │   │  2. 多通道并行搜索（过去24小时滚动≈前一天）   │    │
│  └─────────┘   │     ├─ Tavily（国际 + 部分中文）            │    │
│                │     └─ 百度新闻（国内中文唯一活跃通道）      │    │
│                │       （知乎/B站：代码骨架保留，已停用，    │    │
│                │         不参与本次抓取，未来可重新启用）     │    │
│  ┌─────────┐   │  3. Layer1: URL 指纹去重                   │    │
│  │  cron   │   │  4. Layer2: 标题相关性评分（0 token）       │    │
│  │ 每周一  │   │  5. Layer3: 分桶限额分析（Tavily≤15/国内≤25）  │    │
│  │ 03:30   │   │  6. 写入 ciosh_intel.db                    │    │
│  └─────────┘   │  7. 生成 HTML 日报                         │    │
│       │        │  8. 163 SMTP 直接发送                       │    │
│       │        └────────────────────────────────────────────┘    │
│       │                                                           │
│       └───────▶┌────────────────────────────────────────────┐    │
│                │              weekly_job.py                  │    │
│                │  1. 统计上周（过去7天滚动）各通道关键词产出率 │    │
│                │  2. 从分析结果提取候选新词                   │    │
│                │  3. 更新 keyword_db.json                    │    │
│                │  4. 生成周报（含关键词健康报告）+ 163 直接发送│    │
│                └────────────────────────────────────────────┘    │
│                                                                   │
│                        ↕ SMTP SSL                               │
│  163 → MAIL_TO（主收件） + MAIL_CC（抄送）                       │
│  日报/周报共用统一版式：A-角色摘要 / B-重点情报（高+中两区块）/  │
│                       C-其他情报 / D-关键词健康与退休词           │
└──────────────────────────────────────────────────────────────────┘
```

> **架构约束（硬性）：** 全量关键词搜索，无 URL seed 信源层，无任何手动录入通道，唯一例外是直接编辑 SQLite 数据库。
>
> **定时任务流程（已定稿，唯一模式）：** `cron → python daily_job.py / weekly_job.py → 任务完成 → 163 SMTP 直接发送`。163 邮箱仅作为报告投递通道，不作为任务触发器（§5.1 模式 A 为最终方案，模式 B 已废弃不再考虑）。

---

## 4. 关键词库设计（keyword_db.json）

### 4.1 数据结构

```json
{
  "version": "2026-W23",
  "last_updated": "2026-06-02",
  "next_review": "2026-06-09",
  "keywords": [
    {
      "word": "EHS管理",
      "category": "core",
      "tier": 1,
      "lang": "zh",
      "added_at": "2026-06-04",
      "added_by": "seed",
      "hit_count_total": 0,
      "hit_count_quality": 0,
      "yield_rate": 0.0,
      "last_hit": null,
      "status": "active"
    }
  ],
  "evolution_log": [
    {
      "date": "2026-06-09",
      "added": ["防坠落系统", "工业互联网安全"],
      "retired": ["劳保展"],
      "reason": "yield_rate < 0.1 连续 2 周"
    }
  ],
  "search_config": {
    "date_range_days": 1,
    "max_results_per_keyword": 5,
    "search_provider": "tavily"
  }
}
```

### 4.2 字段说明


| 字段                  | 含义                                         | 自动更新               |
| ------------------- | ------------------------------------------ | ------------------ |
| `tier`              | 1=核心词（每天搜），2=扩展词（每天搜），3=观察词（每周搜）           | 手动 / 系统建议          |
| `hit_count_total`   | 累计搜出的结果数                                   | daily_job          |
| `hit_count_quality` | 累计通过 Layer2 + Layer3 的高质量结果数               | daily_job          |
| `yield_rate`        | `hit_count_quality / hit_count_total`，越高越好 | weekly_job 计算      |
| `status`            | `active` / `paused` / `retired`            | weekly_job 自动 + 手动 |


### 4.3 初始种子词库（Tier 1 核心词，中英文各一组）

**中文核心词（每天搜索）**

```
EHS管理 / 职业健康安全 / 工厂安全生产 / 危化品管理
智能安全帽 / 可穿戴安全设备 / 个人防护装备新技术
工业消防 / 高空作业防护 / 防坠落系统
应急响应 / 安全生产标准 / ISO 45001
环境监测设备 / 职业病防治 / 噪声防护
智慧工厂安全 / 工业物联网安全 / 安全传感器
```

**英文核心词（tier 2，每天搜索，发现国际趋势）**

```
EHS technology exhibition / smart PPE / wearable safety device
industrial safety innovation / occupational health trends
safety monitoring IoT / digital safety management
```

**Tier 3 观察词（每周一次搜索，探索边界）**

```
气体检测仪 / 工业机器人安全 / VR安全培训
建筑工地安全 / 矿山安全设备 / 核电安全防护
食品安全防护用品 / 生物安全防护 / 医疗防护
```

### 4.4 关键词进化规则（weekly_job 执行）

**自动提案（AI 挖掘）**
每周，系统从本周所有 `priority=high` 的分析结果中提取 `keywords` 字段，统计频次，如果某个词在本周出现 ≥3 次且不在词库中，自动写入词库作为 Tier 3 观察词，并在周报中标注"新词提案"，由你决定是否升为 Tier 1。

**自动退休**
连续 2 周 `yield_rate < 0.05`（每20次搜索产出少于1条高质量结果）的词，自动标记 `status=retired`，停止搜索。

**手动控制**
`keyword_db.json` 是普通 JSON 文件，随时可以直接编辑：修改 tier、暂停某词、手动添加词。下次 cron 执行时自动生效。

---

## 5. 定时任务设计

### 5.1 Cron 触发架构

你的约束：cron 在本地 Mac 运行，以 163 邮件形式定时触发。

解读：这里"163 邮件触发"有两层含义，需要确认选择哪种模式：

**模式 A（推荐）：cron 直接调用 Python 脚本，163 仅作为报告投递通道**

```
cron → python daily_job.py → 任务完成 → 163 SMTP 发送日报邮件
```

优点：最简单可靠，不依赖邮件收发延迟，日志清晰。
缺点：需要电脑在 cron 时间点开机。

**模式 B：163 邮件触发（IMAP 轮询方式）**

```
cron 每5分钟检查 163 收件箱 → 发现触发邮件 → 执行任务
```

优点：可以从手机发邮件远程触发任务。
缺点：增加 IMAP 监听复杂度，意义有限（你在家才需要触发，在家就有电脑）。

**本文档按模式 A 设计，且已最终定稿，不再讨论模式 B。** 163 邮箱仅用于发送报告，不用于触发。

> **流程定稿声明（v1.3）：** 全系统唯一的运行路径是
> `cron（launchd/crontab，UTC时间触发）→ python daily_job.py / weekly_job.py（脚本内完成全部步骤）→ 任务正常结束 → 163 SMTP 直接发送邮件`。
> 不存在邮件触发、IMAP 轮询或任何中间环节。`run_daily.sh` / `run_weekly.sh` 只是 cron 调用入口的 shell 包装（负责等待磁盘挂载、选择 Python 解释器、写日志），不改变这条单一路径。本节描述与 §3 架构图、§5.3/§5.4 流程图、`scripts/run_daily.sh`、`scripts/run_weekly.sh`、`scripts/setup_cron.sh` 的实现完全一致，已交叉核对无冲突。

### 5.2 Cron 表达式

```bash
# 每日情报采集（北京时间 03:00）
0 19 * * * /path/to/ciosh/intel/scripts/run_daily.sh >> /path/to/ciosh/intel/logs/cron_daily.log 2>&1

# 每周关键词进化（周一 北京时间 03:30）
30 19 * * 0 /path/to/ciosh/intel/scripts/run_weekly.sh >> /path/to/ciosh/intel/logs/cron_weekly.log 2>&1
```

> ⚠️ macOS cron 使用 UTC 时间。北京时间 03:00 = UTC 19:00（前一天）；周一 03:30 北京 = 周日 UTC 19:30。

### 5.3 日任务流程（daily_job.py）

```
开始（03:00 北京时间）
 │
 ├─ Step 1：加载关键词库（keyword_db.json）
 │          取 tier=1 和 tier=2 的 active 词
 │          本日搜索词单 = Tier1 全部 + Tier2 全部
 │          （Tier3 仅周一执行）
 │
 ├─ Step 2：多通道搜索（时间窗：过去24小时滚动 ≈ "前一天"）
 │          通道：Tavily（days=1）+ 百度新闻（tbs=qdr:d）
 │          知乎 / B站：代码骨架保留（search_zhihu / search_bilibili 仍可单独调用），
 │                      但 search_all_domestic 不再调用它们，停用期间不产生抓取流量
 │          时间语义：均为"过去24小时滚动窗口"，非严格日历昨天
 │          Cron 03:00触发，覆盖 昨天03:00→今天03:00，含今天00-03点内容
 │          这是设计意图：情报系统需要最新内容而非日历切割，
 │          滚动窗口与"前一天"在每日单次执行节奏下基本等价，无需改为日历切割
 │          对每个活跃关键词执行搜索
 │          max_results=5 条/词
 │          记录：关键词 → 原始结果列表（标题 + URL + 摘要）
 │          更新 keyword_db.json 的 hit_count_total
 │
 ├─ Step 3：Layer 1 · URL 指纹去重
 │          对所有搜索结果的 URL 计算 MD5
 │          对比数据库 seen_urls 表（已见 URL 集合）
 │          过滤掉已见的 URL → 只保留增量
 │          将新 URL 批量写入 seen_urls
 │
 ├─ Step 4：Layer 2 · 标题相关性评分（0 token）
 │          对每条结果的标题做简单评分：
 │          - 包含品类关键词 +2 分
 │          - 包含展会/市场/技术/解决方案等信号词 +1 分
 │          - 包含广告词/招聘/无关词 -2 分
 │          分数 ≥ 2 分的条目才进入 Layer 3
 │          目标：从原始结果中过滤掉 60-70% 的噪音
 │
 ├─ Step 5：Layer 3 · 分桶限额 DeepSeek 分析
 │          按 source_channel 分桶：tavily | domestic（当前仅 baidu，zhihu/bilibili 停用不产生数据）
 │          各桶内按 layer2_score 降序排序，取 Top N：
 │            Tavily 桶：LAYER3_CAP_TAVILY 条（默认 15）
 │            国内桶：  LAYER3_CAP_DOMESTIC 条（默认 25）
 │          合并两桶（≤40条）逐条调用 DeepSeek
 │          输出：category / priority / summary_zh / keywords / ciosh_relevance / ciosh_action
 │          批量处理，每 10 条打印进度
 │          更新 keyword_db.json 的 hit_count_quality
 │
 ├─ Step 6：写入数据库（ciosh_intel.db）
 │          分析结果写入 intel_items 表
 │          含原始数据 + 分析结果 + 触发关键词
 │
 ├─ Step 6.5：角色摘要合并生成（单次 DeepSeek 调用）
 │          输入：当日 priority=high+medium 条目
 │          输出 JSON：{ sales_digest, market_digest, ops_digest } 各≤150字
 │          sales_digest：  哪些品类有展商机会 / 对应行业 / 销售切入点
 │          market_digest： 行业价值 / 趋势数据 / 市场话术
 │          ops_digest：    论坛主题 / 展会结构整合 / 新方向与现展结合
 │          失败则降级为空摘要，不阻断后续步骤
 │
 ├─ Step 7：生成统一 HTML 日报（A/B/C/D 四段式，详见 §5.6）
 │          A-角色摘要（销售/市场/运营三行纵排）
 │          B-重点情报（高优先级 / 中优先级两个独立区块，摘要本身即为带下划线超链接）
 │          C-其他情报（低优先级精简列表）
 │          D-关键词健康与退休词（日报展示当日命中快照，结构与周报 D 区块一致）
 │
 └─ Step 8：163 SMTP 发送（单封统一日报，唯一投递路径）
            流程：cron → daily_job.py 跑完全部步骤 → 163 SMTP 直接发送（不经邮件触发）
            收件人：MAIL_TO（主收件） + MAIL_CC（抄送）
            主题：[CIOSH情报] YYYY-MM-DD · N条
结束
```

### 5.4 周任务流程（weekly_job.py）

```
开始（周一 03:30 北京时间，UTC 周日 19:30）
 │
 ├─ Step 1：统计上一周各关键词产出（时间窗：collected_at >= now-7天，滚动窗口 ≈ 上一自然周）
 │          从 intel_items 查询过去 7 天数据
 │          按 source_keyword 分组统计：总命中 / 高质量命中
 │          计算 yield_rate
 │          说明：与日报一致，采用"过去 N 天滚动窗口"而非日历周切割；
 │          weekly_job 固定在周一 03:30 执行，滚动 7 天窗口在此节奏下
 │          覆盖的即为上一个自然周的数据，语义等价，无需改为日历周查询
 │
 ├─ Step 2：关键词退休决策
 │          连续 2 周 yield_rate < 0.05 → status=retired
 │          写入 evolution_log
 │
 ├─ Step 3：从分析结果挖掘候选新词
 │          提取本周所有 priority=high 条目的 keywords 字段
 │          统计词频
 │          不在词库中且频次 ≥ 3 的词 → 生成"新词提案"列表
 │
 ├─ Step 4：更新 keyword_db.json
 │          更新 yield_rate
 │          标记 retired 词
 │          写入新词（tier=3，status=active，added_by="auto"）
 │          更新 version 和 last_updated
 │
 ├─ Step 5：生成统一 HTML 周报（与日报共用同一套 A/B/C/D 模板，详见 §5.6）
 │          A-角色摘要（本周三角色视角纵排小结）
 │          B-重点情报（本周高/中优先级两区块）
 │          C-其他情报（本周低优先级精简列表）
 │          D-关键词健康报告 + 退休词/新词提案（合并为同一区块，参考既有模板设计）
 │
 └─ Step 6：163 SMTP 发送周报（同样 cron → weekly_job.py → 163 SMTP 直接发送，唯一投递路径）
结束
```

### 5.6 邮件版式设计（日报/周报共用统一模板，仅数据来源不同）

> 配色严格沿用 CIOSH 品牌色（GREEN #009040 / ORANGE #f39700 / DARK #221b19 / GRAY_BG #f5f5f5 / BORDER #e0e0e0 / MUTED #999999），本次改动**只调整排版结构，不改配色**。

四段结构，自上而下：

- **A · 角色摘要**：纵向三行（禁止三列并排），依次为"销售视角 / 市场视角 / 运营视角"，字号在原角色卡基础上调小 2 号
- **B · 重点情报**：拆分为两个独立区块——"高优先级"在上、"中优先级"在下；每条情报不再单独放"查看原文"链接，而是把摘要文字本身做成超链接（加下划线），点击摘要即跳转原文
- **C · 其他情报**：仅展示精简摘要（标题/缩略概要），链接样式与现状保持一致（不加下划线），字号在 B 区块基础上调小 4 号
- **D · 关键词健康与退休词**（新增区块）：将"关键词健康报告"（yield_rate 排名表）与"本周退休词 / 新词提案"合并为同一个区块展示，直接参考 `services/reporter.py` 中既有的 `关键词健康报告` 表格样式重排，仅做品牌色对齐，不改变信息结构

> 日报与周报使用同一套构建函数（不再各自维护模板），区别仅在于：日报 D 区块展示"当日"关键词命中快照，周报 D 区块展示"本周"完整健康报告 + 退休词/新词提案。

### 5.5 一次性初始化任务（seed_job.py）

用于项目启动时的历史数据补充，对应你说的"一次性调研"概念。这个脚本只运行一次：

```
seed_job.py：
 │
 ├─ 用初始词库做回溯搜索（Tavily 支持 time_range 参数）
 │  搜索时间范围：过去 90 天
 │  每个词最多取 10 条（建立基线）
 │
 ├─ 走完完整的三层漏斗流程
 │
 └─ 写入数据库，标记 source_type='seed'
    这批数据不发邮件，只建库
```

---

## 6. CIOSH 专属 AI 分析维度

Geckos 的分析器是通用展览行业视角（并购/新展/合作/退出/政策）。CIOSH 需要专属的品类信号识别。

### 6.1 品类信号分类

```python
CIOSH_CATEGORIES = {
    "core_ppe": "传统PPE（手套/服装/面具/面料）",      # 现有主力，监控动向
    "ehs_tech": "EHS科技（智能传感/监控/管理系统）",    # 最重要的新品类方向
    "smart_ppe": "智慧防护（可穿戴/IoT/数字化PPE）",   # 高增长新品类
    "industrial_safety": "工业安全系统（防坠落/机械防护）",
    "fire_safety": "消防安全（设备/系统）",
    "env_monitoring": "环境监测（气体/噪声/粉尘）",
    "emergency_response": "应急响应（设备/培训/演练）",
    "policy_regulatory": "政策法规（新标准/认证要求）",  # 品类进入的信号
    "market_signal": "市场信号（展商动向/采购需求/竞品）",
    "other": "其他"
}
```

### 6.2 CIOSH 专属 System Prompt

```python
CIOSH_SYSTEM_PROMPT = """
你是CIOSH（中国国际劳动保护用品交易会）的品类战略顾问，供职于杜塞尔多夫展览（上海）有限公司。
你的任务是识别可以帮助CIOSH突破单一PPE品类的战略信号。

CIOSH当前困境：展商品类过度集中在低端PPE（手套/劳保服/面料），
需要在2027年前引入新品类展商：EHS科技、智慧防护、工业安全系统等方向。

高优先级信号（直接服务品类引进决策）：
- 某细分品类出现新的头部企业或突破性产品
- 某细分品类的市场规模/增速数据（佐证引进价值）
- 政策法规要求某类新防护设备（创造展商需求）
- 竞展（Safety Expo/A+A/CIOSH友展）新增某品类展团
- 国内展会/行业协会首次提及某品类方向

中优先级信号（背景积累，有价值但不紧急）：
- 行业技术趋势报告
- 企业战略合作或产品发布
- 标准/认证变化

低优先级（噪音，记录但不深度分析）：
- 个别企业融资/人事信息
- 学术研究
- 无明确市场信号的行业动态
"""
```

### 6.3 分析输出格式

```json
{
  "category": "ehs_tech",
  "priority": "high",
  "summary_zh": "中文一句话（≤30字）",
  "ciosh_relevance": "high|medium|low",
  "ciosh_action": "可引进展商品类：XXX / 可用于招商话术：XXX / 建议追踪",
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "new_keyword_suggestion": "防坠落智能设备"
}
```

`ciosh_action` 字段是 CIOSH 雷达区别于 Geckos 最关键的字段：**每条情报直接输出对 CIOSH 的可操作建议**，而不只是信息摘要。

---

## 7. Token 消耗预算与优化策略

### 7.1 每日 Token 消耗估算


| 环节                  | 单次消耗            | 每日数量      | 每日合计                |
| ------------------- | --------------- | --------- | ------------------- |
| Tavily 搜索           | 无 token 消耗      | 全量词 × 5条  | 0                   |
| 百度新闻抓取（国内唯一活跃通道）| 0（requests）     | 全量词 × 5条  | 0                   |
| 知乎 / B站搜索（已停用，不产生抓取量）| 0       | 0         | 0                   |
| Layer 1 URL 去重      | 0 token         | 全部原始结果    | 0                   |
| Layer 2 标题评分        | 0 token（本地计算）   | 全部原始结果    | 0                   |
| Layer 3 DeepSeek 分析 | ~500 token/条    | ≤40条（Tavily≤15 + 国内≤25）| ≤ 20,000 tokens |
| 角色摘要生成（单次合并调用）  | ~800 tokens     | 1次        | 800 tokens          |
| **每日合计**            |                 |           | **≤ 21,000 tokens（约¥0.02/天）** |


使用 DeepSeek-chat（$0.14/M tokens）：**每日成本 ≤ ¥0.02**，每月约 ¥0.6。
分桶方案同时保证中英文信号均衡，成本仅比原 20 条上限增加 ¥0.3/月。

### 7.2 Token 优化关键决策

**决策1：Layer 2 不用 AI，用规则**
标题相关性评分用 Python 关键词匹配，不调用 API。一个函数 50 行代码可以过滤掉 60% 以上的噪音。

**决策2：传入 AI 的内容只有标题 + Tavily 摘要**
不先抓取全文再分析，Tavily 返回的摘要（通常 150-300 字）已经足够 AI 判断 category 和 priority。全文抓取留给用户手动点击查看。

**决策3：按来源通道分桶限额（Bucket Cap）**
Layer2 通过后，按 source_channel 分两个桶，各桶内按 layer2_score 降序取 Top N：
Tavily 桶（`LAYER3_CAP_TAVILY=15`）保证国际信号覆盖；
国内桶（`LAYER3_CAP_DOMESTIC=25`）保证中文政策/行业信号不被英文挤占。
两桶配额可通过 .env 调整，无需改代码。

**决策4：URL 指纹库是长期投资**
每个进入数据库的 URL 都记录下来，后续永不重复分析。随着数据库积累，Layer 1 去掉的比例会越来越高，AI 消耗会逐步降低。

**决策5：报告生成用结构化拼接，不用 AI 重写**
日报的大部分内容是直接展示数据库里已分析好的摘要，AI 只做一个 ≤100 字的今日导言，其余内容零 token。

---

## 8. 数据库设计（ciosh_intel.db）

### 8.1 表结构

```sql
-- 情报条目（核心表）
CREATE TABLE intel_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    url             TEXT UNIQUE,
    snippet         TEXT,              -- Tavily 返回的摘要
    source_name     TEXT,              -- 来源网站名
    pub_date        TEXT,              -- 发布日期（字符串）
    collected_at    TEXT NOT NULL,     -- 采集时间 ISO8601
    source_keyword  TEXT,              -- 触发该结果的关键词
    source_channel  TEXT DEFAULT 'tavily',  -- tavily / baidu（活跃）；zhihu / bilibili（架构保留，已停用）；playwright（不使用）
    layer2_score    REAL,              -- Layer2 相关性评分
    is_analyzed     INTEGER DEFAULT 0, -- 是否已 AI 分析
    is_duplicate    INTEGER DEFAULT 0, -- Layer1 去重标记
    -- AI 分析结果
    category        TEXT,
    priority        TEXT,              -- high / medium / low
    ciosh_relevance TEXT,              -- high / medium / low
    ciosh_action    TEXT,              -- 可操作建议
    summary_zh      TEXT,
    keywords_json   TEXT,              -- JSON 数组字符串
    analyzed_at     TEXT,
    source_type     TEXT DEFAULT 'daily'  -- daily / weekly_tier3 / seed
);

-- URL 指纹表（Layer1 去重用）
CREATE TABLE seen_urls (
    url_hash    TEXT PRIMARY KEY,  -- MD5(url)
    url         TEXT,
    first_seen  TEXT NOT NULL
);

-- 日报记录
CREATE TABLE reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    report_type TEXT DEFAULT 'daily',  -- daily / weekly
    title_zh    TEXT,
    html_body   TEXT,
    sent_at     TEXT,
    item_count  INTEGER DEFAULT 0
);

-- 关键词历史快照（每周存一版，便于回溯）
CREATE TABLE keyword_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label  TEXT NOT NULL,  -- 如 "2026-W24"
    snapshot_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
```

---

## 9. 文件结构

```
AI Project/ciosh/intel/          ← 新建此目录
│
├── DESIGN.md                    ← 本文档（已存在于 ciosh/ 根目录）
│
├── .env                         ← 密钥（不进 git）
│   DEEPSEEK_API_KEY=sk-xxx
│   TAVILY_API_KEY=tvly-xxx
│   SMTP_HOST=smtp.163.com
│   SMTP_PORT=465
│   SMTP_USER=xxx@163.com
│   SMTP_PASSWORD=xxx（163授权码）
│   MAIL_TO=max.wang@mds.cn          # 主收件人（逗号分隔多人）
│   MAIL_CC=boss@mds.cn,team@mds.cn  # 抄送（可选，逗号分隔）
│   LAYER3_CAP_TAVILY=15             # Tavily 桶进入 Layer3 的上限
│   LAYER3_CAP_DOMESTIC=25           # 国内桶进入 Layer3 的上限
│
├── keyword_db.json              ← 活的关键词库（版本化，人工可直接编辑）
│
├── config.py                    ← 项目配置（读取 .env）
│
├── models.py                    ← SQLite 建表 + 连接函数
│
├── services/
│   ├── searcher.py              ← Tavily 搜索封装（国际通道）
│   ├── domestic_searcher.py     ← 国内通道：百度新闻（活跃）｜知乎/B站（代码骨架保留，已停用）
│   ├── layer2_filter.py         ← 标题相关性评分（纯本地，0 token）
│   ├── analyzer.py              ← CIOSH 专属 AI 分析（基于 Geckos analyzer.py 改写）
│   ├── reporter.py              ← HTML 日报/周报生成
│   ├── keyword_evolver.py       ← 关键词进化逻辑（weekly_job 调用）
│   └── mailer.py                ← 163 SMTP 发送（直接复用 Geckos mailer.py）
│
├── scripts/
│   ├── daily_job.py             ← 每日任务入口
│   ├── weekly_job.py            ← 每周任务入口
│   ├── seed_job.py              ← 一次性初始化采集
│   ├── run_daily.sh             ← cron 调用的 shell 包装
│   └── run_weekly.sh            ← cron 调用的 shell 包装
│
├── data/
│   └── ciosh_intel.db           ← SQLite 数据库
│
├── logs/
│   ├── cron_daily.log
│   └── cron_weekly.log
│
└── requirements.txt
    requests + beautifulsoup4   ← 百度新闻抓取
    tavily-python               ← 国际搜索
    bilibili-api-python         ← B站搜索（已停用，依赖暂保留以便未来重新启用，不强制安装）
    python-dotenv
```

---

## 10. 与 Geckos 的代码复用策略


| 模块                                  | 复用策略     | 说明                                           |
| ----------------------------------- | -------- | -------------------------------------------- |
| `mailer.py`                         | **直接复用** | 163 SMTP 逻辑完全相同，复制过来                         |
| `deduplicator.py`                   | **参考复用** | URL MD5 去重逻辑类似，但 CIOSH 用 seen_urls 表，不用相似度比对 |
| `analyzer.py` 底层 `_call_deepseek()` | **提取复用** | 只复用 API 调用和 JSON 解析部分，System Prompt 完全重写     |
| `collector.py`                      | **不复用**  | Geckos 是 URL 爬取，CIOSH 是 Tavily 关键词搜索，逻辑不同    |
| `models.py`                         | **不复用**  | 数据库 schema 不同，独立定义                           |
| `config.py`                         | **参考结构** | 相同的 dotenv 读取模式，独立 .env 文件                   |
| Flask 全部代码                          | **完全不用** | CIOSH 雷达是纯脚本，无 Web 服务                        |


---

## 11. 实施路径（Phase by Phase）

### Phase 0 · 环境准备（1 天）

- 创建 `ciosh/intel/` 目录结构
- 安装依赖：`pip install tavily-python python-dotenv requests`
- 配置 `.env` 文件（DeepSeek Key、Tavily Key、163 SMTP）
- 创建 `keyword_db.json` 初始种子词库（参考本文档第 4.3 节）

### Phase 1 · 数据库与配置层（半天）

- 实现 `models.py`：建表函数 + 连接函数
- 实现 `config.py`：读取 .env
- 运行建表，验证 `ciosh_intel.db` 创建成功

### Phase 2 · 三层漏斗（1.5 天）

- 实现 `searcher.py`：Tavily API 封装，支持 date_range
- 实现 `layer2_filter.py`：标题评分函数，本地规则
- 实现 `analyzer.py`：CIOSH 专属 System Prompt + DeepSeek 调用
- 单元测试：各层输入输出验证

### Phase 3 · 任务脚本（1 天）

- 实现 `daily_job.py`：串联 8 步流程
- 实现 `reporter.py`：HTML 日报模板
- 实现 `mailer.py`：163 SMTP 发送
- 手动运行 daily_job.py，验证全流程

### Phase 4 · 关键词进化（1 天）

- 实现 `keyword_evolver.py`：yield_rate 计算 + 新词提案
- 实现 `weekly_job.py`：串联进化逻辑 + 周报生成
- 手动运行 weekly_job.py，验证词库更新

### Phase 5 · 一次性初始化（半天）

- 实现 `seed_job.py`：90 天回溯采集
- 运行 seed_job，建立基线数据库（预计 200-500 条）

### Phase 6 · Cron 接入（半天）

- 编写 `run_daily.sh` 和 `run_weekly.sh`（绝对路径）
- 配置 crontab
- 验证首次自动运行

### Phase 7 · 国内数据通道 + Skill 层激活（3 天）

> **前置条件：** Phase 0–6 全部完成并稳定运行至少 1 周。
> **执行方：** Claude Code，参考 `MISSION_PHASE7.md`（本 Phase 完成后生成）。

**7-A：国内搜索通道（`services/domestic_searcher.py`）**

实现三个并行搜索通道，统一返回与 `searcher.py` 相同的 dict schema（含 `source_channel` 字段）：

- **百度新闻**：`search_baidu(word, date_range_days, max_results)` → 抓取 `news.baidu.com?tn=news&word={word}&tbs=qdr:d`，解析标题/摘要/来源，`source_channel="baidu"`，词间间隔 2–3 秒
- **知乎**（**已停用**）：`search_zhihu(word, date_range_days, max_results)` → 函数与解析逻辑完整保留在 `domestic_searcher.py` 中，可独立调用验证，但不再被 `search_all_domestic` 调度，可信度过低，暂不参与日常抓取
- **B站**（**已停用**）：`search_bilibili(word, date_range_days, max_results)` → 同上，函数骨架与依赖（`bilibili-api-python`）保留，不再被调度，未来如需重新启用，只需把它加回 `search_all_domestic` 的调用列表
- **统一入口**：`search_all_domestic(word, date_range_days, max_results_each)` → 当前只调用 `search_baidu`，合并结果返回；`search_zhihu`/`search_bilibili` 留在模块内但不在调用链上，任一通道失败不影响其他

`daily_job.py` 的 Step 2 改为调用 Tavily + domestic（百度）合并结果后统一进漏斗。

**7-B：Skill 层接口激活**

将 Phase 2 中两个硬编码改为从文件读取：

- `analyzer.py`：System Prompt 改为读取 `skills/analyzer_prompt/` 目录下版本号最大的 `.md` 文件正文
- `layer2_filter.py`：评分词表和权重改为读取 `skills/layer2_rules/` 目录下版本号最大的 `.json` 文件

两处均需要缓存（模块级变量），避免每次调用重复读文件。

**7-C：Skill 进化脚本（`services/skill_evolver.py`）**

实现四个函数，由 `weekly_job.py` 在现有进化逻辑之后依次调用：

- `evolve_layer2_rules(conn, skills_dir)` → 统计 Layer2 评分区间与 priority 交叉频次，连续 3 周低效词降权，写入新版本 `layer2_rules/v{n+1}.json`
- `evolve_analyzer_prompt(conn, skills_dir)` → 提取本周高/低优先级样本，调用 DeepSeek 生成 ≤3 条优化提案，写入 `analyzer_prompt/proposals/YYYY-WXX.md`（最低门槛：本周分析条目 ≥ 10）
- `evolve_category_briefs(conn, skills_dir)` → 按品类生成本周增量摘要，追加到对应 brief 文件；每 4 周执行月度浓缩重写
- `refresh_skill_summary(conn, keyword_db_path, skills_dir)` → 覆写 `skills/SKILL.md`，更新系统状态快照

**7-D：Phase 7 验收标准**

```
[ ] domestic_searcher.py 三通道均可独立搜索并返回正确 source_channel
[ ] daily_job.py 合并四通道后，原始结果数较 Phase 6 增加 50% 以上
[ ] analyzer.py 成功从 skills/analyzer_prompt/v1.md 读取 prompt，不再硬编码
[ ] layer2_filter.py 成功从 skills/layer2_rules/v1.json 读取权重
[ ] weekly_job.py 执行后 skills/SKILL.md 自动更新时间戳
[ ] weekly_job.py 执行后 skills/analyzer_prompt/proposals/ 生成当周提案文件
[ ] 运行结果写入 MISSION_PHASE7_RESULT.md，Cowork Claude 二次校验
```

---

## 12. 关键风险与预案


| 风险                   | 可能性 | 预案                                      |
| -------------------- | --- | --------------------------------------- |
| Tavily API 无法搜到昨天的内容 | 中   | 调整 date_range 为最近 3 天，daily 去重保证不重复分析   |
| Layer2 过滤过于激进（漏掉好内容） | 中   | 初期设低阈值（≥1分通过），观察 2 周后调整                 |
| DeepSeek API 超时      | 低   | 单条超时跳过，整批失败时日报仍发送（附 "AI 分析暂不可用" 提示）     |
| Mac 休眠导致 cron 未执行    | 高   | 在 run_daily.sh 中检查当天日志，如果当天已跑过则跳过（幂等设计） |
| 关键词膨胀（词库越来越大）        | 中   | yield_rate 退休机制自动控制，上限设 50 个活跃词         |
| 163 邮件发送失败           | 低   | 重试 2 次，失败后写入日志，次日随日报附带补发提示              |


---

## 13. 成功标准

**2 周后**：

- 每天收到日报邮件，平均 5-15 条有效情报
- 词库已自动退休 ≥2 个低效词，新增 ≥1 个 AI 提案词
- 数据库积累 100+ 条情报

**1 个月后**：

- 已识别出 ≥3 个有具体展商候选的新品类方向（ciosh_action 字段有明确指向）
- Layer2 过滤率稳定在 60% 以上（说明词库质量在提升）
- 词库 Tier 1 词的 yield_rate 平均值 ≥0.20

**3 个月后**：

- 情报数据库可以直接支撑"2027 CIOSH 新品类引进提案"的数据论证
- 词库已经历 ≥2 轮完整的进化周期，形成真正反映 CIOSH 新品类边界的热词图谱

---

## 附录 A：国内多通道搜索设计

### A.1 各通道定位


| 通道     | 目标内容             | 技术方案                           | 状态   |
| ------ | ---------------- | ------------------------------ | ----- |
| Tavily | 国际媒体、英文行业报告、部分中文 | `tavily-python` SDK            | 活跃 |
| 百度新闻   | 国内新闻、政府公告、行业媒体   | `requests` 抓取 `news.baidu.com` | 活跃（国内唯一通道） |
| 知乎     | 行业讨论、专家观点、问答     | `requests` 解析 `__NEXT_DATA__`  | **已停用**（可信度过低，函数与解析逻辑保留，未接入调度） |
| B站     | 产品展示视频、行业科普内容    | `bilibili-api-python` 包        | **已停用**（可信度过低，函数骨架与依赖保留，未接入调度） |

> 知乎 / B站停用原因：实测可信度（标题相关性、内容质量）显著低于百度新闻，且反爬限制更严格，长期投入产出比不划算。两个通道的代码、`source_channel` 枚举值、数据库 schema 均完整保留，未来若评估认为有必要，只需把它们重新加入 `search_all_domestic` 的调用链即可恢复，无需重写。

### A.2 百度新闻抓取规范

```
URL 模式：https://www.baidu.com/s?tn=news&word={keyword}&tbs=qdr:d
解析目标：标题（h3/h4）+ 来源（span.c-author）+ 摘要（span.c-line-clamp2）
时间过滤：tbs=qdr:d（昨天）
注意：设置合理 User-Agent 和间隔（每词间隔 2-3 秒），避免触发反爬
```

### A.3 社交平台通道（Phase 7 → 现状：已停用）

知乎和 B站曾作为社交采集通道纳入架构，但 Phase 7 上线运行后评估其可信度过低，已停用（不参与抓取调度，代码与依赖保留以便未来重新启用）；抖音因 App 级反爬，从设计之初即排除，不在系统范围内。


---

## 14. Skill 层设计：越用越聪明的四轮进化

> **核心原则：** Skill 层是能力的沉淀，不是数据的积累。
> **执行节奏：** 全部四轮进化与周报同频，由 `weekly_job.py` 统一驱动，每周一 03:30 执行。

---

### 14.1 四层进化架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    CIOSH Intel Skill 层                      │
│                                                              │
│  第一层：探测能力进化（Keyword Skill）                        │
│  每周：yield_rate 计算 → 退休低效词 → 提案新词               │
│  存储：keyword_db.json                                       │
│                          ↓ 数据飞轮                         │
│  第二层：过滤能力进化（Filter Skill）                         │
│  每周：Layer2 评分 vs Layer3 priority 相关性统计             │
│  → 自动调整评分词表权重（减少 token 浪费）                    │
│  存储：skills/layer2_rules/v{n}.json                        │
│                          ↓ 能力飞轮                         │
│  第三层：判断能力进化（Analyzer Skill）                       │
│  每周：提取高低优先级样本模式 → 生成 prompt 优化提案          │
│  → BD 总监确认后写入新版本（人在回路，不自动覆盖）             │
│  存储：skills/analyzer_prompt/v{n}.md                       │
│                          ↓ 知识飞轮                         │
│  第四层：品类智识进化（Category Skill）                       │
│  每周：各品类信号密度 + 增量摘要 → 累积品类情报简报           │
│  → 反哺下一周的 analyzer 背景知识                            │
│  存储：skills/category_briefs/{category}.md（滚动追加）      │
│                                                              │
│  SKILL.md（神经中枢）：每周自动覆写，Agent 进入必读           │
└─────────────────────────────────────────────────────────────┘
```

---

### 14.2 第一层：Keyword Skill（探测能力）

**已在 Phase 4 实现，此处为完整定义。**

每周 `weekly_job.py` 执行：

- 连续 2 周 `yield_rate < 0.05` → 自动退休
- 从本周 `priority=high` 条目的 `keywords_json` 提取频次 ≥ 3 的新词 → 写入 Tier 3
- 产出：`keyword_db.json` 更新 + 周报"词库变动"板块

---

### 14.3 第二层：Filter Skill（过滤能力）

**新增函数：`evolve_layer2_rules()` → 由 `weekly_job.py` 调用**

目标：Layer2 评分权重随数据积累变准，减少"通过 Layer2 但 Layer3 判为 low"的 token 浪费。

每周执行逻辑：

```
1. 查询本周 is_analyzed=1 的条目
2. 统计 layer2_score 区间 × priority 的交叉频次
3. 计算各词类的"有效命中率" = high_count / total_count
4. 某词类连续 3 周有效命中率 < 0.2 → 标记"待降权"
5. 连续 3 周处于待降权 → 自动写入 skills/layer2_rules/v{n+1}.json
   将该词权重降一档（+2→+1 或 +1→0）
6. 反向：连续 3 周有效命中率 > 0.4 → 自动升权
```

`layer2_filter.py` 启动时读取 `skills/layer2_rules/` 目录下最新版本，自动生效，无需改代码。

版本化存储示例：

```json
{
  "version": 2,
  "generated_at": "2026-06-30",
  "positive_weights": {
    "EHS": 2, "展会": 1, "解决方案": 0.5, "防坠落": 2
  },
  "evolution_note": "「解决方案」降权：3周有效命中率0.08，多为广告内容"
}
```

---

### 14.4 第三层：Analyzer Skill（判断能力）

**新增函数：`evolve_analyzer_prompt()` → 由 `weekly_job.py` 调用**

目标：让 DeepSeek 的分析判断越来越贴近 CIOSH 实际业务需求。

**人在回路设计（提案自动生成，应用需人工确认）：**

```
每周执行：
1. 取本周 priority=high 的全部条目（title + ciosh_action + keywords）
2. 取本周 priority=low 但 layer2_score 较高的样本（高估条目）
3. 发送给 DeepSeek，请其输出 ≤3 条 prompt 优化建议
   （最低数据门槛：本周分析条目 ≥ 10 条，否则跳过）
4. 输出写入：skills/analyzer_prompt/proposals/YYYY-WXX.md
5. 周报邮件包含"本周 Prompt 进化提案"板块，BD 总监确认后手动更新版本
```

`analyzer.py` 从 `skills/analyzer_prompt/` 目录读取最新版本，而非硬编码。

存储结构：

```
skills/analyzer_prompt/
├── v1.md          ← 初始版本
├── v2.md          ← 第一次人工确认更新
└── proposals/
    └── 2026-W24.md  ← AI 自动提案（待人工审核）
```

---

### 14.5 第四层：Category Skill（品类智识）

**新增函数：`evolve_category_briefs()` → 由 `weekly_job.py` 调用**

目标：把每周积累的品类信号转化为可复用的品类智识，反哺分析能力，最终支撑 CIOSH 新品类引进决策。

每周执行逻辑：

```
1. 按 category 统计本周新增 high+medium priority 条目
2. 对条目数 ≥ 3 的品类，生成本周增量摘要（DeepSeek，≤100字）
3. 将增量摘要追加到 skills/category_briefs/{category}.md 末尾
4. 每 4 周做一次月度浓缩：对全文做结构化重写，合并前4周增量
```

**品类简报反哺 Analyzer：**

`weekly_job` 执行 Layer3 分析前，将各品类简报的"核心信号"段注入 DeepSeek user prompt 背景（不修改 system prompt，只作为上下文）。这使每次分析都带有历史背景，大幅减少重复发现相同信号的问题。

品类简报格式：

```markdown
# EHS 科技 · 品类情报简报

> 最后更新：2026-W26 | 累计情报：47条 | 综合热度：★★★★☆

## 当前核心信号（最近4周浓缩）
[月度自动生成]

## 周度增量
### 2026-W26
[本周新增信号摘要]

## CIOSH 引进可行性评估
[BD 总监手动维护]
```

---

### 14.6 SKILL.md：神经中枢（每周自动覆写）

`ciosh/intel/skills/SKILL.md` 是整个 Skill 层对外的统一入口。任何 Agent 进入项目时读此文件，立刻理解系统当前的能力状态。

由 `weekly_job.py` 每周末自动覆写，内容包括：

- 累计情报条目数 / 词库活跃词数
- 当前分析 Prompt 版本
- 本周品类热度排名（按情报密度）
- 词库本周变动（新增 / 退休）
- 待审核 Prompt 提案链接
- 当前分析焦点与 BD 决策建议

---

### 14.7 Skill 层文件结构

```
ciosh/intel/skills/
├── SKILL.md                       ← 神经中枢，每周自动覆写
├── analyzer_prompt/
│   ├── v1.md                      ← 初始 prompt（Phase 2 从代码提取）
│   └── proposals/
│       └── YYYY-WXX.md            ← 每周自动提案
├── layer2_rules/
│   └── v1.json                    ← 初始规则（Phase 2 从代码提取）
└── category_briefs/
    ├── ehs_tech.md
    ├── smart_ppe.md
    ├── industrial_safety.md
    ├── fire_safety.md
    ├── env_monitoring.md
    ├── emergency_response.md
    └── policy_regulatory.md
```

---

### 14.8 Phase 2 预留接口（不阻塞主流程）

Phase 2 实现时需预留两个接口，Phase 7 直接激活，无需改代码：

1. `analyzer.py`：System Prompt 改为从 `skills/analyzer_prompt/` 读取最新版本，而非硬编码字符串
2. `layer2_filter.py`：评分权重改为从 `skills/layer2_rules/` 读取最新版本，而非硬编码列表

---

## 附录 B：四轮进化飞轮

```
更好的关键词（第一层）
    → 更多高质量原始结果
    → 更准的 Layer2 过滤权重（第二层）
    → 更少 token 浪费，更多有效分析
    → 更准的 Analyzer Prompt（第三层）
    → 分析判断力提升
    → 更丰富的品类信号积累
    → 更完整的品类简报（第四层）
    → 反哺 Analyzer 背景知识
    → 更准确的 high/low 判断
    → yield_rate 数据更真实
    → 回到更好的关键词（第一层）
```

每跑一周，飞轮转一圈。系统不是在"运行"，是在"学习"。

---


## 15. 云端部署设计（预留图纸）

> 当前为本地 Mac 运行，本节为未来迁移阿里云的完整设计图纸。
> 迁移成本：rsync 同步文件 + 重配 .env + 重设 crontab，约 30 分钟。

### 15.1 目标架构（服务器版）

```
┌──────────────────────────────────────────────────────────────┐
│            阿里云轻量应用服务器（上海节点）                     │
│            推荐配置：2核 2GB 20GB，约¥24-40/月               │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    crontab (UTC)                      │   │
│  │  0 19 * * *   → daily_job.py  （北京 03:00）         │   │
│  │  30 19 * * 0  → weekly_job.py （北京周一 03:30）     │   │
│  └──────────────────────────────────────────────────────┘   │
│                         ↓                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ciosh/intel/                                        │   │
│  │    .env           ← 服务器独立 .env（不同路径）      │   │
│  │    data/          ← SQLite（原生文件系统，无WAL问题） │   │
│  │    logs/          ← logrotate 每周清理               │   │
│  │    skills/        ← Skill 层文件持久化               │   │
│  └──────────────────────────────────────────────────────┘   │
│                         ↓ SMTP SSL                           │
│  163 邮箱 ──────────────────────────── 三角色收件人          │
└──────────────────────────────────────────────────────────────┘
```

### 15.2 本地 vs 服务器关键差异

| 项目 | 本地 Mac | 阿里云服务器 |
|---|---|---|
| SQLite WAL 模式 | 挂载限制，需关闭 | 原生文件系统，正常启用 |
| cron 时区 | macOS 用 UTC 计算 | Linux cron UTC，行为一致 |
| 网络访问 Tavily/DeepSeek | 直连，延迟低 | 大陆节点偶有延迟，try/except 兜底 |
| 百度新闻抓取 | 正常 | 大陆节点正常 |
| Playwright（Phase 7） | 本地安装 Chromium | 服务器需 `playwright install chromium` + 额外依赖 |
| 日志查看 | 直接打开文件 | SSH + `tail -f logs/cron_daily.log` |
| 机器睡眠/重启 | 会导致 cron 跳过 | 24/7 在线，不存在此问题 |

### 15.3 迁移检查清单（当前本地稳定运行 2+ 周后执行）

```
[ ] rsync -avz ciosh/intel/ user@server:/path/to/ciosh/intel/
    --exclude='.env' --exclude='data/' --exclude='logs/'
[ ] 在服务器上创建 .env（填入与本地相同的 API keys）
[ ] 确认服务器 Python 版本 >= 3.10
[ ] pip install -r requirements.txt --break-system-packages
[ ] python models.py   （初始化空数据库）
[ ] python scripts/seed_job.py   （90天回溯，仅一次）
[ ] bash scripts/setup_cron.sh   （查看 crontab 行）
[ ] crontab -e   （添加两行）
[ ] 手动触发 daily_job.py 验证邮件收到
[ ] 确认 logs/ 目录下 logrotate 配置（防止日志无限增长）
```

### 15.4 服务器专属配置差异（.env 新增项）

```bash
# 服务器版 .env 额外配置
DB_PATH=/home/user/ciosh/intel/data/ciosh_intel.db
KEYWORD_DB_PATH=/home/user/ciosh/intel/keyword_db.json
LOG_DIR=/home/user/ciosh/intel/logs

# 服务器上 SQLite 可启用 WAL（本地挂载不支持，服务器原生文件系统支持）
SQLITE_WAL_MODE=1
```

---
*CIOSH 情报雷达 · 设计规划书 v1.2 · 2026-06-04（更新：2026-06-05）*
*文档位置：ciosh/2026-06-04_S09_intel_radar_design.md*