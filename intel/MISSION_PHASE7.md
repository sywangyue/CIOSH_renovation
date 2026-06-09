# CIOSH Intel Radar — Execution Mission: Phase 7 (v2)

> **Executor:** Claude Code
> **Reviewer:** Cowork Claude (secondary verification after completion)
> **Pre-read required:** `CLAUDE.md` + `skills/SKILL.md` + `../docs/2026-06-04_S10_intel_radar_design.md` Section 11 Phase 7
> **This is v2:** Adds multi-role email (Task 7-F), removes Layer3 cap (Task 7-B update), removes 小红书
> **Working directory:** All files in `ciosh/intel/` unless stated otherwise
> **Pre-condition:** Phase 0–6 complete and running stably

---

## Before You Start

```bash
cd /path/to/AI\ Project/ciosh/intel

# Confirm Phase 6 is working
python -c "
import sqlite3
conn = sqlite3.connect('data/ciosh_intel.db')
print('intel_items:', conn.execute('SELECT COUNT(*) FROM intel_items').fetchone()[0])
print('seen_urls:', conn.execute('SELECT COUNT(*) FROM seen_urls').fetchone()[0])
conn.close()
"
# Expected: intel_items >= 35, seen_urls >= 333

# Install new deps
pip install bilibili-api-python --break-system-packages -q
```

---

## Task 7-A: `services/domestic_searcher.py`

Three domestic search channels. Each function must return a list of dicts with exactly these keys:
`title`, `url`, `snippet`, `source_name`, `pub_date`, `source_keyword`, `source_channel`

On any exception: print error, return `[]`. Never raise.

### Channel 1: Baidu News

```python
def search_baidu(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]:
    """
    Scrape https://www.baidu.com/s?tn=news&rn=20&word={word}&tbs=qdr:d
    tbs=qdr:d = yesterday's news
    
    Parse strategy:
    - Find all <h3> or <h4> tags containing <a> → title + href
    - Find adjacent source/date spans for source_name and pub_date
    - snippet: text of the next sibling div/p after the title tag
    
    Headers: User-Agent = realistic Chrome/macOS string, Accept-Language: zh-CN,zh
    Rate limit: time.sleep(2) between calls when batching keywords
    source_channel = "baidu"
    """
```

### Channel 2: Zhihu

```python
def search_zhihu(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]:
    """
    GET https://www.zhihu.com/search?type=content&q={word}
    
    Parse strategy:
    - Extract JSON from <script id="__NEXT_DATA__"> tag
    - Navigate: props.pageProps.searchResult.items (or similar path — inspect actual response)
    - Filter items where created_time/updated_time is within date_range_days
    - Map: title, url (https://zhuanlan.zhihu.com/p/{id} or /question/{id}/answer/{id}),
           excerpt as snippet, author_name as source_name
    
    Fallback: if __NEXT_DATA__ parse fails, return []
    source_channel = "zhihu"
    """
```

### Channel 3: Bilibili

```python
def search_bilibili(word: str, date_range_days: int = 1, max_results: int = 5) -> list[dict]:
    """
    Use bilibili-api-python (sync wrapper around async API).
    Search type: article (专栏) preferred, video fallback.
    
    import asyncio
    from bilibili_api import search
    
    result = asyncio.run(search.search_by_type(
        keyword=word,
        search_type=search.SearchObjectType.ARTICLE,
        page=1
    ))
    
    Filter results by pubdate within date_range_days.
    Map: title, url, desc as snippet, author as source_name.
    source_channel = "bilibili"
    """
```

### Unified entry point

```python
def search_all_domestic(word: str, date_range_days: int = 1, max_results_each: int = 5) -> list[dict]:
    """Call all three channels sequentially (not concurrent — avoid rate limits).
    Concatenate results. Return flat list. Never raises."""
```

**Verify:**
```bash
python -c "
import sys; sys.path.insert(0, '.')
from services.domestic_searcher import search_baidu, search_zhihu, search_bilibili

for fn, name in [(search_baidu,'baidu'),(search_zhihu,'zhihu'),(search_bilibili,'bilibili')]:
    r = fn('EHS管理', max_results=2)
    ch = r[0].get('source_channel','MISSING') if r else 'no results'
    print(f'{name}: {len(r)} results, channel={ch}')
"
```

---

## Task 7-B: Wire `daily_job.py` — domestic channels + remove Layer3 cap + role digest

In `scripts/daily_job.py`, make three changes:

**Change 1 — Multi-channel search (Step 2):**
```python
from services.searcher import search_keywords
from services.domestic_searcher import search_all_domestic

tavily_results = search_keywords(active_keywords, days_back=1)
domestic_results = []
for kw in active_keywords:
    domestic_results.extend(search_all_domestic(kw, date_range_days=1, max_results_each=3))
raw_results = tavily_results + domestic_results
print(f"Step 2: Tavily {len(tavily_results)} + 国内 {len(domestic_results)} = {len(raw_results)} 条")
```

**Change 2 — Replace hard cap with Bucket Cap:**

In `scripts/daily_job.py` Step 5, replace the simple `batch_analyze(passed_items)` call with bucket logic:

```python
def _bucket_cap(items: list[dict], cap_tavily: int, cap_domestic: int) -> list[dict]:
    """Split by source_channel, sort by layer2_score desc, take Top N each bucket."""
    tavily = sorted([i for i in items if i.get('source_channel','') == 'tavily'],
                    key=lambda x: x.get('layer2_score', 0), reverse=True)[:cap_tavily]
    domestic = sorted([i for i in items if i.get('source_channel','') != 'tavily'],
                      key=lambda x: x.get('layer2_score', 0), reverse=True)[:cap_domestic]
    return tavily + domestic

cap_tavily  = int(os.getenv('LAYER3_CAP_TAVILY', '15'))
cap_domestic = int(os.getenv('LAYER3_CAP_DOMESTIC', '25'))
to_analyze = _bucket_cap(layer2_passed, cap_tavily, cap_domestic)
print(f"Step 5 bucket: Tavily {sum(1 for i in to_analyze if i.get('source_channel')=='tavily')} "
      f"+ 国内 {sum(1 for i in to_analyze if i.get('source_channel')!='tavily')} 条进入Layer3")
analyzed_items = batch_analyze(to_analyze)
```

Add `import os` at top of daily_job.py if not already present.
`_bucket_cap` is a local helper function defined inside `run_daily()` or at module level — keep it simple, no separate file.

Also update `config.py`: add two new fields:
```python
LAYER3_CAP_TAVILY:   int = int(os.getenv('LAYER3_CAP_TAVILY', '15'))
LAYER3_CAP_DOMESTIC: int = int(os.getenv('LAYER3_CAP_DOMESTIC', '25'))
```

**Verify bucket logic:**
```python
# After running daily_job.py, check the Step 5 log line:
# Expected: "Step 5 bucket: Tavily X + 国内 Y 条进入Layer3" where X<=15, Y<=25
```

**Change 3 — Role digest call (Step 6.5, NEW):**
After batch_analyze, before building reports, call:
```python
from services.role_reporter import synthesize_role_digests
role_digests = synthesize_role_digests(analyzed_items)  # single DeepSeek call
# role_digests = {sales_digest: str, market_digest: str, ops_digest: str}
```

**Change 4 — Single unified email (Step 7-8):**
```python
from services.role_reporter import build_unified_html
from services.mailer import send_report

html = build_unified_html(analyzed_items, role_digests, today)
send_report(
    subject=f'[CIOSH情报] {today} · {len(analyzed_items)}条',
    html_body=html
)  # uses MAIL_TO + MAIL_CC from config, no changes needed
```

---

## Task 7-C: Activate Skill layer interfaces

### 7-C1: `services/analyzer.py` — load prompt from file

Replace the hardcoded `_SYSTEM_PROMPT` string with a file loader:

```python
def _load_system_prompt() -> str:
    """Load latest versioned prompt from skills/analyzer_prompt/.
    Falls back to hardcoded default if directory/file missing."""
    skills_dir = Path(__file__).resolve().parent.parent / "skills" / "analyzer_prompt"
    if not skills_dir.exists():
        return _DEFAULT_SYSTEM_PROMPT  # keep original string as fallback
    # Find highest version: v1.md, v2.md, ... → pick max by version number
    versions = sorted(skills_dir.glob("v*.md"), key=lambda p: int(p.stem[1:]))
    if not versions:
        return _DEFAULT_SYSTEM_PROMPT
    return versions[-1].read_text(encoding="utf-8").split("## System Prompt")[-1].strip()

# Module-level cache (load once per process)
_SYSTEM_PROMPT = _load_system_prompt()
```

Rename the existing hardcoded string to `_DEFAULT_SYSTEM_PROMPT`. Do NOT change the prompt content.

### 7-C2: `services/layer2_filter.py` — load rules from file

```python
def _load_rules() -> dict:
    """Load latest versioned rules from skills/layer2_rules/.
    Falls back to hardcoded defaults if missing."""
    import json
    skills_dir = Path(__file__).resolve().parent.parent / "skills" / "layer2_rules"
    if not skills_dir.exists():
        return None
    versions = sorted(skills_dir.glob("v*.json"), key=lambda p: int(p.stem[1:]))
    if not versions:
        return None
    with open(versions[-1], encoding="utf-8") as f:
        return json.load(f)

_rules = _load_rules()

# Use _rules["category_terms"] etc. if loaded, else fall back to hardcoded lists
_CATEGORY_TERMS = _rules["category_terms"] if _rules else [...]  # keep existing list as fallback
_SIGNAL_TERMS   = _rules["signal_terms"]   if _rules else [...]
_NOISE_TERMS    = _rules["noise_terms"]    if _rules else [...]
```

**Verify:**
```python
from services.analyzer import _SYSTEM_PROMPT
assert "skills/analyzer_prompt" not in _SYSTEM_PROMPT  # content loaded, not path
assert "CIOSH" in _SYSTEM_PROMPT
print("analyzer prompt loaded from file:", len(_SYSTEM_PROMPT), "chars")

from services.layer2_filter import _CATEGORY_TERMS
assert "EHS" in _CATEGORY_TERMS
print("layer2 rules loaded:", len(_CATEGORY_TERMS), "category terms")
```

---

## Task 7-D: `services/skill_evolver.py`

Four functions, all called by `weekly_job.py` after existing evolution logic.

### `evolve_layer2_rules(conn, skills_dir: Path)`

```
1. Query this week's intel_items: layer2_score × priority cross-tabulation
2. For each term type (category/signal/noise): compute effective_hit_rate = high_count/total
3. Track consecutive_low_weeks: if effective_hit_rate < 0.2 for 3 weeks → mark for downgrade
4. If any downgrades pending: write new v{n+1}.json with adjusted weights
   (category_terms_weight: 2→1, or signal_terms_weight: 1→0.5)
5. Log changes in evolution_log array within the JSON
Minimum data gate: skip if total analyzed items this week < 10
```

### `evolve_analyzer_prompt(conn, skills_dir: Path)`

```
1. Fetch this week's priority=high items (title + ciosh_action + keywords_json)
2. Fetch sample of priority=low items where layer2_score >= 2 (over-estimated)
3. Minimum data gate: skip if high_items < 3
4. Call DeepSeek with prompt asking for ≤3 system prompt improvement suggestions
5. Write output to skills_dir/analyzer_prompt/proposals/YYYY-WXX.md
   Format: date header + numbered suggestions + raw sample data appended
```

### `evolve_category_briefs(conn, skills_dir: Path)`

```
1. For each category with >= 3 new high+medium items this week:
   a. Collect titles + summaries
   b. Call DeepSeek: "用≤100字总结本周{category}品类的新增信号"
   c. APPEND to skills_dir/category_briefs/{category}.md:
      ### {YYYY-WXX}\n{summary}\n\n
2. Every 4th week (week_number % 4 == 0): full rewrite of the brief
   (condense all weekly entries into structured summary, keep last 4 weeks detail)
```

### `refresh_skill_summary(conn, keyword_db_path: Path, skills_dir: Path)`

```
Overwrite skills/SKILL.md with current system state:
- Timestamp, week label
- intel_items count, seen_urls count, active keywords count
- Current analyzer prompt version (latest vN.md filename)
- This week's category heat ranking (by intel count)
- Keyword changes this week (from keyword_db evolution_log)
- Link to latest proposal file if exists
- Known gaps section (update as gaps are resolved)
```

---

## Task 7-E: Wire `weekly_job.py`

After the existing `evolve_keywords()` call, add:

```python
from services.skill_evolver import (
    evolve_layer2_rules, evolve_analyzer_prompt,
    evolve_category_briefs, refresh_skill_summary
)
from pathlib import Path

skills_dir = Path(__file__).resolve().parent.parent / "skills"

print("Skill进化：Layer2规则...")
evolve_layer2_rules(conn, skills_dir)

print("Skill进化：Analyzer Prompt提案...")
evolve_analyzer_prompt(conn, skills_dir)

print("Skill进化：品类简报...")
evolve_category_briefs(conn, skills_dir)

print("Skill进化：更新SKILL.md...")
refresh_skill_summary(conn, cfg.KEYWORD_DB_PATH, skills_dir)
```

Each call wrapped in try/except — failure prints error and continues, never aborts weekly job.

---

---

## Task 7-F: `services/role_reporter.py` (REVISED)

One file, two functions. **One unified HTML email** covering all three roles — no separate templates.

---

### `synthesize_role_digests(items: list[dict]) -> dict`

Single DeepSeek call. Input: day's `priority=high` or `priority=medium` analyzed items (max 30 for this call).

**System prompt (exact):**
```
你是CIOSH情报雷达的报告合成器。基于当日情报，为三个角色各生成一段≤200字的中文摘要。
每段摘要必须用多行bullet points格式（每条以"• "开头），禁止段落文字。
销售：聚焦哪些具体品类/行业有展商机会，以及对应的销售切入点。
市场：聚焦行业市场价值、趋势数据、可用于客户沟通的市场话术。
运营：聚焦论坛主题方向、新品类与现有展会结构的整合建议。
```

**Output JSON (strict):**
```json
{
  "sales_digest": "• 第一条\n• 第二条\n• 第三条",
  "market_digest": "• 第一条\n• 第二条",
  "ops_digest": "• 第一条\n• 第二条"
}
```

Fallback: if items < 3 or API fails, return `{"sales_digest":"","market_digest":"","ops_digest":""}`.

---

### `build_unified_html(items: list[dict], role_digests: dict, date_str: str) -> str`

Returns a single complete HTML string (inline CSS, no external deps).

**Color constants (must use exactly, no other colors):**
```python
GREEN  = "#009040"   # CIOSH brand green — headers, HIGH badge, links
ORANGE = "#f39700"   # CIOSH brand orange — MED badge, market section accent
DARK   = "#221b19"   # body text
WHITE  = "#ffffff"
GRAY_BG= "#f5f5f5"   # section backgrounds
BORDER = "#e0e0e0"   # dividers
MUTED  = "#999999"   # LOW priority text, meta info
FONT   = "'Helvetica Neue',Helvetica,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',Arial,sans-serif"
```

**Email HTML structure (implement in this exact order):**

```
[Header]
  Background: GREEN | Text: WHITE
  Left: "CIOSH 情报雷达" (18px bold) | Right: date_str + " · N条"

[Part A — 角色摘要]
  Section title: "A  角色摘要" — 13px, MUTED, uppercase letter-spacing
  Three role blocks side by side (or stacked on narrow clients):

  [销售视角]              [市场视角]              [运营视角]
  Border-left: GREEN     Border-left: ORANGE    Border-left: GREEN
  Title: 13px bold DARK  Title: 13px bold DARK  Title: 13px bold DARK
  Content: bullet lines  Content: bullet lines  Content: bullet lines
  (14px, DARK, line-height 1.6)
  If digest is empty: show "今日数据不足，暂无摘要" in MUTED

  Helper: parse "• line1
• line2" → render each as <div style="...">• line</div>

[Divider: 1px solid BORDER]

[Part B — 高/中优先级情报]
  Section title: "B  重点情报" — 13px, MUTED
  For each item where priority in ('high','medium'):
    [Badge] HIGH → background GREEN, text WHITE, 11px
            MED  → background ORANGE, text WHITE, 11px
    [Category tag] 12px, color GREEN, background #e8f5e9
    [Summary] item['summary_zh'] — 14px, DARK
    [Link] "→ 查看原文" — GREEN, 13px, href=item['url']
    Separator: 1px dashed BORDER between items

[Divider: 1px solid BORDER]

[Part C — 低优先级情报]
  Section title: "C  其他情报" — 13px, MUTED
  Compact list: for each item where priority == 'low':
    <div>• <a href="{url}" style="color:{GREEN}">{title}</a>
         <span style="color:{MUTED};font-size:12px"> [{category}]</span></div>

[Footer]
  Background: GRAY_BG | Border-top: 1px solid BORDER
  Text: "CIOSH 情报雷达 · 自动生成" — 12px MUTED centered
```

**Verify:**
```python
import sys; sys.path.insert(0, '.')
from services.role_reporter import synthesize_role_digests, build_unified_html
items = [
    {"title":"EHS智能安全帽IoT联网","priority":"high","category":"smart_ppe",
     "summary_zh":"某公司发布可穿戴安全设备","url":"https://example.com","ciosh_action":"可引进智能PPE"},
    {"title":"安全生产标准修订","priority":"medium","category":"policy_regulatory",
     "summary_zh":"新国标正式实施","url":"https://example2.com","ciosh_action":""},
    {"title":"某企业人事变动","priority":"low","category":"other",
     "summary_zh":"某公司更换CEO","url":"https://example3.com","ciosh_action":""},
]
digests = synthesize_role_digests(items)
html = build_unified_html(items, digests, "2026-06-05")
assert "#009040" in html, "GREEN color missing"
assert "#f39700" in html, "ORANGE color missing"
assert "销售视角" in html
assert "市场视角" in html
assert "运营视角" in html
assert "重点情报" in html
assert "其他情报" in html
print("OK, html length:", len(html))
```

---

## Task 7-G: Update `daily_job.py` email step (REVISED)

**Remove** the 3-route email loop added in Task 7-B Change 4.
**Replace** with single unified send:

```python
from services.role_reporter import build_unified_html, synthesize_role_digests

# Step 6.5: role digest (single DeepSeek call)
role_digests = synthesize_role_digests(analyzed_items)

# Step 7: one unified HTML
html = build_unified_html(analyzed_items, role_digests, today)

# Step 8: send once
send_report(
    subject=f"[CIOSH情报] {today} · {len(analyzed_items)}条",
    html_body=html
)
# send_report already reads MAIL_TO and MAIL_CC from config — no changes to config.py needed
```

**Also remove** `MAIL_TO_SALES`, `MAIL_TO_MARKET`, `MAIL_TO_OPS` from `config.py` if they were added in any previous step. Keep only `MAIL_TO` + `MAIL_CC`.

---

## Deliverables Checklist

```
[ ] services/domestic_searcher.py  — 3 channels (baidu/zhihu/bilibili) + unified entry
[ ] services/role_reporter.py      — synthesize_role_digests + build_unified_html (CIOSH colors)
[ ] daily_job.py updated           — domestic channels + no Layer3 cap + role digest + single send
[ ] analyzer.py updated            — prompt loaded from skills/analyzer_prompt/
[ ] layer2_filter.py updated       — rules loaded from skills/layer2_rules/
[ ] services/skill_evolver.py      — 4 evolution functions
[ ] weekly_job.py updated          — skill_evolver calls wired in
[ ] config.py verified             — only MAIL_TO + MAIL_CC, no role-specific fields
[ ] Phase 7 manual run output      — write to MISSION_PHASE7_RESULT.md
```

## Phase 7 Verification

```bash
cd /path/to/ciosh/intel

# Test domestic channels
python -c "
from services.domestic_searcher import search_baidu, search_zhihu, search_bilibili
for fn, name in [(search_baidu,'baidu'),(search_zhihu,'zhihu'),(search_bilibili,'bilibili')]:
    r = fn('EHS管理', max_results=2)
    print(f'{name}: {len(r)} results')
"

# Test unified HTML email
python -c "
from services.role_reporter import synthesize_role_digests, build_unified_html
items = [{'title':'Test','priority':'high','category':'ehs_tech',
          'summary_zh':'Test summary','url':'http://test.com','ciosh_action':'Test action'}]
d = synthesize_role_digests(items)
html = build_unified_html(items, d, '2026-06-05')
assert '#009040' in html
assert '销售视角' in html
print('HTML OK, length:', len(html))
"

# Run full daily job (sends one email)
python scripts/daily_job.py

# Run weekly job
python scripts/weekly_job.py

# Check skills/ updated
ls -la skills/analyzer_prompt/proposals/
cat skills/SKILL.md | head -20
```

---

*CIOSH Intel Radar · Execution Mission Phase 7 v2 · 2026-06-05*
*Issued by: Cowork Claude | To be executed by: Claude Code*


## Phase 7 Verification Run

```bash
cd /path/to/ciosh/intel

# Test domestic channels
python -c "
from services.domestic_searcher import search_baidu, search_zhihu, search_bilibili
for fn, name in [(search_baidu,'baidu'),(search_zhihu,'zhihu'),(search_bilibili,'bilibili')]:
    r = fn('EHS管理', max_results=2)
    print(f'{name}: {len(r)} results')
"

# Run daily job (should now pull from 4 channels)
python scripts/daily_job.py

# Run weekly job (should update skills/)
python scripts/weekly_job.py

# Check skills/ updated
ls -la skills/
ls -la skills/analyzer_prompt/proposals/
cat skills/SKILL.md | head -20
```

Write results (raw terminal output + file listing of `skills/`) to `MISSION_PHASE7_RESULT.md`.
Cowork Claude will verify: channel coverage, SKILL.md freshness, proposal file existence.

---

## Cross-Cutting Rules (CLAUDE.md)

- **Hello Max** on every response
- **Surgical**: do NOT rewrite daily_job.py or weekly_job.py from scratch — only add the wiring
- **Token discipline**: domestic max_results_each=3, Layer3 cap unchanged at 20
- **No fallback removal**: keep all hardcoded defaults as fallbacks — file loading is additive

---

*CIOSH Intel Radar · Execution Mission Phase 7 v2 · 2026-06-05*
*Issued by: Cowork Claude | To be executed by: Claude Code*
