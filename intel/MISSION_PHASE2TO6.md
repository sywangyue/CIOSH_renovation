# CIOSH Intel Radar — Execution Mission: Phase 2 → 6

> **Executor:** Claude Code
> **Reviewer:** Cowork Claude (secondary verification after completion)
> **Pre-read required:** `CLAUDE.md` (same directory) + `../2026-06-04_S09_intel_radar_design.md`
> **Working directory:** All files go into `ciosh/intel/` unless stated otherwise

---

## Before You Start — Mandatory Checks

```bash
cd /path/to/AI\ Project/ciosh/intel

# 1. Confirm .env exists and has real values (not placeholders)
cat .env | grep -E "^(DEEPSEEK|TAVILY|SMTP|MAIL)" | sed 's/=.*/=***/'

# 2. Confirm Python env and deps
pip install tavily-python python-dotenv requests --break-system-packages -q
python -c "from dotenv import load_dotenv; print('dotenv OK')"
python -c "from tavily import TavilyClient; print('tavily OK')"

# 3. Initialize DB on real filesystem (not sandbox)
python models.py
# Expected: "数据库初始化完成: /.../data/ciosh_intel.db"
```

---

## Phase 2 — Three-Layer Funnel

### 2-A: `services/searcher.py` (Tavily — international channel)

Implement Tavily search wrapper. Requirements:
- Function: `search_keyword(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]`
- Each returned dict must contain: `title`, `url`, `snippet`, `source_name`, `pub_date` (best-effort), `source_keyword`, `source_channel="tavily"`
- Use `TavilyClient` from `tavily-python` package
- `search_depth="basic"` (cheaper), `topic="news"`
- For `date_range_days=1`, pass `days=1` to Tavily's `search()`
- On any exception: print error, return `[]` — never raise

**Verify:**
```python
from services.searcher import search_keyword
results = search_keyword("EHS管理", date_range_days=1, max_results=3)
print(f"Got {len(results)} results")
if results: print(results[0].get("source_channel"))  # Expected: "tavily"
```

---

### 2-A2: `services/domestic_searcher.py` (Baidu / Zhihu / Bilibili)

Three domestic channels, each as a standalone function with the same return dict schema as searcher.py.

**Channel 1: Baidu News**
```python
def search_baidu(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]:
    """
    Scrape news.baidu.com search results.
    URL: https://www.baidu.com/s?tn=news&word={word}&tbs=qdr:d
    tbs=qdr:d = yesterday; qdr:w = last week
    Parse: h3/h4 title tags with <a> links, span.c-author for source, snippet text
    Headers: realistic User-Agent, Accept-Language: zh-CN
    Rate limit: sleep 2-3 seconds between keyword calls
    source_channel = "baidu"
    """
```

**Channel 2: Zhihu**
```python
def search_zhihu(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]:
    """
    Search Zhihu public content (no login needed for search results).
    URL: https://www.zhihu.com/search?type=content&q={word}
    Parse the JSON embedded in __NEXT_DATA__ script tag — it contains search results.
    Filter results by created/updated time to respect date_range_days.
    source_channel = "zhihu"
    Fallback: if __NEXT_DATA__ parse fails, return []
    """
```

**Channel 3: Bilibili**
```python
def search_bilibili(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]:
    """
    Search Bilibili articles and videos using bilibili-api-python.
    Use sync_bilibili_api wrapper (bilibili_api is async — use asyncio.run()).
    Search type: article (专栏) preferred over video for text content.
    Filter by pubdate within date_range_days.
    source_channel = "bilibili"
    Map: title, url (BV link or article link), snippet (description), source_name="bilibili"
    """
```

**Unified entry point:**
```python
def search_all_domestic(word: str, date_range_days: int = 1, max_results_each: int = 5) -> list[dict]:
    """Call all three channels, concatenate, return flat list. Never raises."""
```

**Master function (used by daily_job.py):**
```python
# In searcher.py or a new search_dispatcher.py — either is fine:
def search_all_channels(keywords: list[dict], date_range_days: int = 1) -> list[dict]:
    """
    For each active keyword:
      - Call Tavily search_keyword()
      - Call domestic search_all_domestic()
    Concatenate all results. Return flat list with source_channel populated.
    """
```

**Install:**
```bash
pip install bilibili-api-python beautifulsoup4 --break-system-packages
```

**Verify:**
```python
from services.domestic_searcher import search_baidu, search_zhihu, search_bilibili
r = search_baidu("EHS管理", max_results=2)
print("baidu:", len(r), r[0].get("source_channel") if r else "no results")
r = search_zhihu("智能安全帽", max_results=2)
print("zhihu:", len(r), r[0].get("source_channel") if r else "no results")
r = search_bilibili("工业安全", max_results=2)
print("bilibili:", len(r), r[0].get("source_channel") if r else "no results")
```

---

### 2-B: `services/layer2_filter.py`

Local relevance scoring — zero API calls. Requirements:

```python
# Scoring rules (additive):
POSITIVE_SIGNALS = {
    # +2 points each — strong CIOSH category signals
    "zh": ["EHS", "职业健康", "安全生产", "防护装备", "劳动保护", "工业安全",
           "安全帽", "防坠落", "可穿戴", "安全传感", "消防", "应急响应",
           "危化品", "职业病", "环境监测", "智慧工厂", "物联网安全"],
    "en": ["EHS", "PPE", "safety", "protective", "occupational health",
           "industrial safety", "wearable", "sensor", "hazard", "compliance"]
}

CONTEXT_SIGNALS = {
    # +1 point each — useful context words
    "zh": ["展会", "市场", "技术", "解决方案", "系统", "设备", "标准", "法规",
           "政策", "认证", "采购", "展商", "行业", "趋势", "创新"],
    "en": ["exhibition", "market", "technology", "solution", "standard",
           "regulation", "certification", "industry", "trend"]
}

NEGATIVE_SIGNALS = {
    # -2 points each — noise
    "zh": ["招聘", "求职", "房产", "彩票", "游戏", "娱乐", "明星", "八卦"],
    "en": ["job", "hiring", "real estate", "casino", "entertainment"]
}
```

- Function: `score_item(item: dict) -> float` — scores title + snippet combined
- Function: `filter_items(items: list[dict], min_score: float = 1.0) -> list[dict]`
  - Adds `layer2_score` field to each passing item
  - Returns only items with score >= min_score

**Verify:**
```python
from services.layer2_filter import score_item
print(score_item({"title": "EHS智能安全帽新技术展会", "snippet": "工业安全解决方案"}))
# Expected: >= 3.0
print(score_item({"title": "明星八卦娱乐新闻", "snippet": ""}))
# Expected: <= -2.0
```

---

### 2-C: `services/analyzer.py`

CIOSH-specific DeepSeek analyzer. Requirements:

**System prompt (use exactly):**
```
你是CIOSH（中国国际劳动保护用品交易会）的品类战略顾问，供职于杜塞尔多夫展览（上海）。
你的任务是识别可以帮助CIOSH突破单一PPE品类的战略信号。

CIOSH当前困境：展商品类过度集中在低端PPE（手套/劳保服/面料），
需要在2027年前引入新品类展商：EHS科技、智慧防护、工业安全系统等方向。

优先级判断：
- high：某品类出现市场信号（新企业/数据/政策/竞展新增该品类）
- medium：行业技术趋势、企业合作、标准变化
- low：个别融资/人事/学术/无明确市场信号
```

**Output JSON schema (strict):**
```json
{
  "category": "ehs_tech|smart_ppe|industrial_safety|fire_safety|env_monitoring|emergency_response|policy_regulatory|market_signal|core_ppe|other",
  "priority": "high|medium|low",
  "ciosh_relevance": "high|medium|low",
  "ciosh_action": "one actionable sentence for CIOSH BD team (≤30 chars zh)",
  "summary_zh": "one sentence summary (≤30 chars)",
  "keywords": ["kw1", "kw2", "kw3"],
  "new_keyword_suggestion": "optional new keyword if signal is strong, else null"
}
```

- Copy `_call_deepseek()` and `_parse_json_from_text()` logic from `../../Geckos/geckos/services/analyzer.py` — do NOT import from there, copy the code
- Function: `analyze_item(item: dict) -> dict` — enriches item dict with analysis fields
- Function: `batch_analyze(items: list[dict], limit: int = 20) -> list[dict]`
  - Hard cap at `limit` items (token budget enforcement)
  - Print progress every 5 items
  - Single item failure → skip and continue

**Verify (uses real API — confirm key is set first):**
```python
import os; assert os.getenv("DEEPSEEK_API_KEY"), "Set DEEPSEEK_API_KEY first"
from services.analyzer import analyze_item
result = analyze_item({"title": "工厂智能安全帽IoT联网实现实时定位", "snippet": "某公司发布新型可穿戴安全设备", "source_keyword": "智能安全帽"})
print(result.get("category"), result.get("priority"), result.get("summary_zh"))
# Expected: category in valid list, priority in {high,medium,low}, summary non-empty
```

---

## Phase 3 — Task Scripts

### 3-A: `services/reporter.py`

HTML daily report generator. Requirements:
- Function: `generate_daily_html(items: list[dict], date_str: str) -> str`
- Returns complete HTML string (inline CSS, no external deps)
- Structure:
  - Header: "CIOSH 情报雷达 · {date_str} 日报"
  - Stats bar: "今日新增 N 条 | 高优先级 X 条 | 搜索关键词 Y 个"
  - High priority section (red/orange accent)
  - Medium priority section
  - Low priority section (collapsed/small)
  - Each item shows: title (linked), source_keyword tag, category tag, ciosh_action, summary_zh
- Function: `generate_weekly_html(stats: dict, keyword_changes: dict, date_str: str) -> str`
  - `stats`: `{category: count}` dict for the week
  - `keyword_changes`: `{added: [], retired: [], proposed: []}` 
  - Returns HTML weekly keyword health report

### 3-B: `services/mailer.py`

Copy `services/mailer.py` from `../../Geckos/geckos/services/mailer.py`. Then:
- Replace all config reads with `from config import get_config`
- Make sure `send_html_email(subject: str, html_body: str, to: str = None) -> bool` works with 163 SMTP SSL on port 465
- Remove any Flask app_context dependency

**Verify (sends real email — do this last):**
```python
from services.mailer import send_html_email
ok = send_html_email("CIOSH 测试邮件", "<h1>Hello Max</h1><p>Phase 3 mailer OK</p>")
print("Sent:", ok)
```

### 3-C: `services/keyword_evolver.py`

Weekly keyword evolution logic. Requirements:
- Function: `compute_yield_rates(db_conn, week_start: str, week_end: str) -> dict[str, float]`
  - Queries `intel_items` grouped by `source_keyword` for the week
  - Returns `{keyword: yield_rate}` where yield_rate = high_quality_count / total_count
- Function: `find_new_keyword_proposals(db_conn, week_start: str, week_end: str, existing_words: set) -> list[str]`
  - Extracts `keywords_json` from all `priority='high'` items in the week
  - Counts frequency
  - Returns words with freq >= 3 that are NOT in `existing_words`
- Function: `update_keyword_db(keyword_db_path: str, yield_rates: dict, new_proposals: list) -> dict`
  - Loads `keyword_db.json`
  - Updates `yield_rate` for each keyword
  - Marks `status=retired` for keywords with yield_rate < 0.05 for 2 consecutive weeks (use `low_yield_weeks` counter field — add it if not present)
  - Appends new proposals as tier=3 active keywords (`added_by="auto"`)
  - Writes updated JSON back to file
  - Returns `{retired: [...], added: [...]}`

---

### 3-D: `scripts/daily_job.py`

Main daily pipeline. Must implement exactly the 8-step flow from S09 design doc section 5.3:

```python
"""
CIOSH 情报雷达 · 每日任务
Cron: 0 19 * * * (UTC) = 北京时间 03:00
"""
```

Steps:
1. Load keyword_db.json, get tier 1+2 active keywords (+ tier 3 if it's Monday)
2. `search_all_keywords()` → raw results, update `hit_count_total` in keyword_db
3. Layer 1: URL MD5 dedup against `seen_urls` table, insert new URLs
4. Layer 2: `filter_items()` with `min_score=cfg.LAYER2_MIN_SCORE`
5. Layer 3: `batch_analyze()` with `limit=cfg.MAX_LAYER3_PER_DAY`, update `hit_count_quality`
6. Write analyzed items to `intel_items` table
7. `generate_daily_html()` → save to `reports` table
8. `send_html_email()` with subject `[CIOSH情报] {date} 日报 · {N}条新情报`

Error handling: each step wrapped in try/except, failure prints error and continues. Never abort the pipeline mid-run.

Idempotency guard at top:
```python
# If today's report already exists in DB, skip and exit
```

### 3-E: `scripts/weekly_job.py`

Weekly evolution pipeline:
1. Compute this week's date range (Mon–Sun)
2. `compute_yield_rates()` for the week
3. `find_new_keyword_proposals()`
4. `update_keyword_db()` → get changes dict
5. Save keyword snapshot to `keyword_snapshots` table
6. `generate_weekly_html()` with stats + changes
7. Send weekly email: `[CIOSH情报] {week} 关键词健康报告`

### 3-F: `scripts/seed_job.py`

One-time historical backfill (run once, never by cron):
- Same pipeline as daily_job but `date_range_days=90`, `max_results=10` per keyword
- Mark all inserted items with `source_type='seed'`
- No email sent
- Print summary at end: total collected, passed layer2, analyzed

---

## Phase 4 — Shell Wrappers + Cron Setup

### `scripts/run_daily.sh`

```bash
#!/bin/bash
# CIOSH Intel Radar — daily job wrapper
# Cron: 0 19 * * *  (UTC 19:00 = Beijing 03:00)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Use system python3 or venv if exists
if [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily_job starting"
"$PYTHON" scripts/daily_job.py
echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily_job done (exit $?)"
```

```bash
chmod +x scripts/run_daily.sh
chmod +x scripts/run_weekly.sh
```

### `scripts/run_weekly.sh`

Same pattern, calls `weekly_job.py`.

### `scripts/setup_cron.sh`

Script that prints the exact crontab lines to add (does NOT modify crontab automatically — let user confirm):

```bash
#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo ""
echo "Add the following lines to your crontab (run: crontab -e):"
echo ""
echo "# CIOSH Intel Radar"
echo "0 19 * * * $PROJECT_DIR/scripts/run_daily.sh >> $PROJECT_DIR/logs/cron_daily.log 2>&1"
echo "30 19 * * 0 $PROJECT_DIR/scripts/run_weekly.sh >> $PROJECT_DIR/logs/cron_weekly.log 2>&1"
echo ""
echo "Note: Times are UTC. Beijing 03:00 = UTC 19:00 (previous calendar day)"
```

---

## Phase 5 — Integration Test (Manual Run)

Run the full pipeline manually before enabling cron:

```bash
cd /path/to/ciosh/intel

# Step 1: Init DB
python models.py

# Step 2: Run seed job (90-day backfill, ~30-60 min depending on keyword count)
python scripts/seed_job.py

# Step 3: Run daily job manually (simulates what cron will do)
python scripts/daily_job.py

# Step 4: Check DB
python -c "
import sqlite3
conn = sqlite3.connect('data/ciosh_intel.db')
print('intel_items:', conn.execute('SELECT COUNT(*) FROM intel_items').fetchone()[0])
print('seen_urls:', conn.execute('SELECT COUNT(*) FROM seen_urls').fetchone()[0])
print('reports:', conn.execute('SELECT COUNT(*) FROM reports').fetchone()[0])
conn.close()
"

# Step 5: Run weekly job
python scripts/weekly_job.py

# Step 6: Setup cron (review output, then add manually)
bash scripts/setup_cron.sh
```

---

## Deliverables Checklist

```
[ ] services/searcher.py         — Tavily search wrapper
[ ] services/layer2_filter.py    — Title scoring (0 token)
[ ] services/analyzer.py         — CIOSH DeepSeek analyzer
[ ] services/reporter.py         — HTML report generator
[ ] services/mailer.py           — 163 SMTP sender
[ ] services/keyword_evolver.py  — Weekly keyword evolution
[ ] scripts/daily_job.py         — Daily 8-step pipeline
[ ] scripts/weekly_job.py        — Weekly evolution pipeline
[ ] scripts/seed_job.py          — One-time backfill
[ ] scripts/run_daily.sh         — Cron shell wrapper
[ ] scripts/run_weekly.sh        — Cron shell wrapper
[ ] scripts/setup_cron.sh        — Cron setup helper
[ ] Phase 5 manual run output    — Screenshot or log excerpt
```

When complete, paste the Phase 5 output (DB record counts + email received confirmation) into a file named `MISSION_RESULT.md` in this directory. Cowork Claude will then perform secondary verification.

---

## Cross-Cutting Rules (from CLAUDE.md)

- **Hello Max**: Every response starts with this
- **Simplicity First**: No features beyond spec. No extra abstractions.
- **Surgical**: Don't touch `config.py`, `models.py`, `keyword_db.json`, `CLAUDE.md` unless a step explicitly requires it
- **Token discipline**: `batch_analyze()` hard cap at `MAX_LAYER3_PER_DAY` — never bypass this
- **No Flask, no Web**: Pure scripts only
- **No cross-project imports**: Copy Geckos code into this project, don't import from `../../Geckos/`

---

*CIOSH Intel Radar · Execution Mission Phase 2→6 · 2026-06-04*
*Issued by: Cowork Claude | To be executed by: Claude Code*
