# CIOSH Intel Radar — Execution Mission: Phase 7

> **Executor:** Claude Code
> **Reviewer:** Cowork Claude (secondary verification after completion)
> **Pre-read required:** `CLAUDE.md` + `skills/SKILL.md` + `../2026-06-04_S09_intel_radar_design.md` Section 11 Phase 7
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

## Task 7-B: Wire `daily_job.py` to use domestic channel

In `scripts/daily_job.py`, find Step 2 (search). Add domestic search alongside Tavily:

```python
# Step 2: multi-channel search
from services.searcher import search_keywords
from services.domestic_searcher import search_all_domestic

tavily_results = search_keywords(active_keywords, days_back=1)

domestic_results = []
for kw in active_keywords:
    domestic_results.extend(search_all_domestic(kw, date_range_days=1, max_results_each=3))

raw_results = tavily_results + domestic_results
print(f"Step 2完成：Tavily {len(tavily_results)} 条 + 国内通道 {len(domestic_results)} 条 = {len(raw_results)} 条")
```

**Constraint:** domestic max_results_each=3 (not 5) to keep total volume manageable. Layer3 hard cap remains 20.

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

## Deliverables Checklist

```
[ ] services/domestic_searcher.py  — 3 channels + unified entry
[ ] daily_job.py updated           — domestic channel wired in Step 2
[ ] analyzer.py updated            — prompt loaded from skills/analyzer_prompt/
[ ] layer2_filter.py updated       — rules loaded from skills/layer2_rules/
[ ] services/skill_evolver.py      — 4 evolution functions
[ ] weekly_job.py updated          — skill_evolver calls wired in
[ ] Phase 7 manual run output      — see verification below
```

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

*CIOSH Intel Radar · Execution Mission Phase 7 · 2026-06-04*
*Issued by: Cowork Claude | To be executed by: Claude Code*
