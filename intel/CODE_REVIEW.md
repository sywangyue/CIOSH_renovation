# CIOSH 情报雷达 · 代码审计报告

> 审计时间：2026-06-08
> 覆盖文件：config.py · models.py · services/searcher.py · services/domestic_searcher.py · services/layer2_filter.py · services/analyzer.py · services/reporter.py · services/role_reporter.py · services/keyword_evolver.py · services/mailer.py · services/skill_evolver.py · scripts/daily_job.py · scripts/weekly_job.py · scripts/seed_job.py
> 审计员：Claude Sonnet 4.6（对抗性审计模式）

---

## CRITICAL（必须修复，影响数据正确性或主流程可靠性）

---

### CR-01 · `models.py:23-87` · `init_db()` 连接泄漏，每次调用都未关闭 executescript 连接

**问题**：`init_db()` 内第 23 行调用 `get_db()` 拿到一个连接，在 `executescript` 之后执行 `conn.close()`（第 87 行）。但如果 `executescript` 抛出异常（如磁盘满、权限错），`conn.close()` 不会被执行，导致数据库句柄泄漏。由于此函数在 `daily_job.py` 和 `weekly_job.py` 里每次启动都调用，在 cron 环境中反复发生会耗尽 SQLite 连接数，最终导致后续 `get_db()` 调用挂起或失败。

**建议修复**：
```python
def init_db() -> None:
    conn = get_db()
    try:
        conn.executescript("""...""")
        try:
            conn.execute("ALTER TABLE intel_items ADD COLUMN source_channel TEXT DEFAULT 'tavily'")
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()
```

---

### CR-02 · `scripts/daily_job.py:60-84` · `_write_intel_items` 在循环内逐条 INSERT，异常后 conn 不一致

**问题**：函数在 for 循环结尾统一 `conn.commit()`（第 84 行），但循环内捕获的 `Exception` 包含 `IntegrityError` 以外的真实错误。如果发生非 UNIQUE 约束的数据库错误（如锁定、磁盘满），循环会继续执行并在最后 commit，可能把部分损坏状态提交，或者使未完成的事务悬空。同样的问题在 `scripts/seed_job.py:45-72` 的 `_write_seed_items` 中存在。

**建议修复**：区分 `sqlite3.IntegrityError`（正常跳过）和其他异常（应 raise 或回滚）：
```python
import sqlite3
for item in items:
    try:
        conn.execute("INSERT OR IGNORE INTO intel_items ...")
    except sqlite3.IntegrityError:
        pass  # UNIQUE 冲突，正常跳过
    except Exception as e:
        print(f"  写入错误（非约束）：{e}")
        conn.rollback()
        raise
conn.commit()
```

---

### CR-03 · `services/analyzer.py:55` · `_load_system_prompt()` 版本排序用 `int(p.stem[1:])` 可能崩溃

**问题**：`sorted(skills_dir.glob("v*.md"), key=lambda p: int(p.stem[1:]))` 在文件名非纯数字时（如 `v1_draft.md`、`v10b.md`）会抛出 `ValueError`，让整个模块加载失败。由于 `_SYSTEM_PROMPT = _load_system_prompt()` 是模块级调用，一旦异常会导致所有导入 `analyzer` 的模块（`daily_job`、`weekly_job`、`seed_job`、`skill_evolver`）全部无法导入，整个流程静默崩溃。同样问题存在于 `services/layer2_filter.py:28` 和 `services/skill_evolver.py:40`。

**建议修复**：
```python
def _safe_version(p: Path) -> int:
    try:
        return int(p.stem[1:])
    except ValueError:
        return -1

versions = sorted(skills_dir.glob("v*.md"), key=_safe_version)
versions = [v for v in versions if _safe_version(v) >= 0]  # 过滤非法文件名
```

---

### CR-04 · `services/role_reporter.py:98-108` · `_bullet_block` 直接将 LLM 返回文本拼入 HTML，存在 XSS 注入风险

**问题**：`_bullet_block(text)` 将 DeepSeek 返回的内容直接嵌入 f-string HTML（第 104-107 行），未做任何 HTML 转义。如果 LLM 返回含 `<script>` 或 `<img onerror=...>` 的内容（无论恶意还是格式混乱），将被邮件客户端执行。同样风险存在于 `reporter.py` 的 `_item_card`、`role_reporter.py` 的 `_item_row_b`、`_item_row_c`，title/summary_zh/ciosh_action 字段均未转义。

**建议修复**：对所有来自外部（LLM / 网络抓取）的字段在插入 HTML 时使用 `html.escape()`：
```python
import html as _html
# 使用时：
f'<div ...>{_html.escape(ln)}</div>'
f'<div ...>{_html.escape(summary)}</div>'
```

---

### CR-05 · `scripts/daily_job.py:112-232` · `main()` 中 `conn` 在异常时不关闭

**问题**：`conn = get_db()` 在第 118 行获取，`conn.close()` 在第 230 行调用。但中间任何未捕获的异常（如 `search_keywords` 网络故障抛出非预期异常、`batch_analyze` 崩溃等）都会绕过 `conn.close()`，导致数据库连接和文件锁泄漏。在 cron 环境中，下一次触发可能遭遇文件锁冲突。同样问题存在于 `weekly_job.py:26-137`。

**建议修复**：
```python
conn = get_db()
try:
    # 主流程
    ...
finally:
    conn.close()
```

---

## HIGH（影响逻辑正确性或健壮性，应尽快修复）

---

### HI-01 · `scripts/daily_job.py:87-106` · `_update_keyword_hits` 在函数内部 import，且无异常保护

**问题**：第 103-104 行在函数体内执行 `from datetime import date as _date`，这是不必要的做法（文件顶部已有 `from datetime import datetime, timedelta`，可直接用 `datetime.now().strftime(...)` 替代）。更重要的是：该函数直接写入 `keyword_db.json` 文件，但如果 `json.dump` 中途失败（如磁盘满），文件会被截断为部分写入状态，造成 JSON 损坏，下次启动时 `json.load` 抛出 `JSONDecodeError`，词库永久损坏。

**建议修复**：原子写入：
```python
import tempfile, os
tmp = path.with_suffix(".tmp")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(db, f, ensure_ascii=False, indent=2)
os.replace(tmp, path)  # 原子替换，POSIX 保证
```
同样修复 `weekly_job.py:68-69` 和 `keyword_evolver.py` 中所有写 `keyword_db.json` 的位置。

---

### HI-02 · `services/domestic_searcher.py:34` · 百度新闻 URL 硬编码 `tbs=qdr:d`，`date_range_days` 参数完全无效

**问题**：`search_baidu(word, date_range_days=1, ...)` 在第 34 行将 URL 写死为 `tbs=qdr:d`（仅过去 1 天）。`date_range_days` 参数被接受但从未被使用，`seed_job.py` 调用 `search_all_domestic(kw, date_range_days=1, ...)` 时无感知，但若未来改成 `date_range_days=90`，`search_baidu` 仍然只返回 1 天内的结果，导致 seed 回溯静默失效。

**建议修复**：
```python
# 百度时间范围映射
_BAIDU_TBS = {1: "qdr:d", 7: "qdr:w", 30: "qdr:m"}
tbs = _BAIDU_TBS.get(date_range_days, "qdr:d")
url = f"https://www.baidu.com/s?tn=news&rn=20&word={quote(word)}&tbs={tbs}"
```

---

### HI-03 · `services/analyzer.py:98-112` · `_parse_json_from_text` 最后一行 `return json.loads(s)` 与第一次尝试重复，且异常不传播

**问题**：函数第 101-103 行已经尝试过 `json.loads(s)` 并失败（进入 `except` 后 pass）。如果文本不以 ``` 开头且不是合法 JSON，第 112 行再次执行 `json.loads(s)` 会抛出与第一次相同的 `JSONDecodeError`，但调用方 `analyze_item`（第 146 行）会捕获它并降级为 `"AI分析失败"`。逻辑没有 bug，但代码含义混乱。真正的问题是：当文本是 ` ```json ... ``` ` 格式但内部 JSON 无效时，第 111 行 `json.loads("\n".join(lines))` 抛出异常，未被任何 try/except 覆盖，会直接向上传播到 `analyze_item` 并触发全局降级——这是预期行为，但代码路径不对称，容易误读。

**建议修复**：将整个解析逻辑包在一个 try/except 中，明确意图：
```python
def _parse_json_from_text(text: str) -> dict[str, Any]:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return json.loads(s)  # 让调用方处理 JSONDecodeError
```

---

### HI-04 · `services/skill_evolver.py:50-63` · `evolve_layer2_rules` 在 `low_weeks < 3` 时直接覆写当前版本文件

**问题**：第 61-63 行，当连续低效周数未达阈值时，将 `consecutive_low_weeks` 计数更新后**覆写** `versions[-1]`（当前生产版本文件）。这意味着每周都会修改 `v1.json` 的内容，破坏了版本文件的不变性（immutability）。若写入中途失败（磁盘满），当前版本规则文件被损坏，`layer2_filter.py` 下次加载会失败。

**建议修复**：用独立的状态文件存储 `consecutive_low_weeks`，不修改版本规则文件本身：
```python
state_path = rules_dir / "_state.json"
state = json.loads(state_path.read_text()) if state_path.exists() else {}
low_weeks = state.get("consecutive_low_weeks", 0)
# ... 计算逻辑 ...
state["consecutive_low_weeks"] = low_weeks
state_path.write_text(json.dumps(state, indent=2))
```

---

### HI-05 · `services/skill_evolver.py:200-215` · 月度浓缩（`evolve_category_briefs`）读入最多 2000 字符，截断处可能切断 Markdown 结构

**问题**：第 203 行 `existing[:2000]` 按字节/字符截断历史简报文件后传给 DeepSeek，在 2000 字符处很可能切断一个段落或标题，导致 LLM 接收到不完整的上文，生成质量不稳定。更严重的是：如果 DeepSeek 返回失败（第 215 行 except），会降级调用 `_append_to_brief`，但月度浓缩本应重写文件，降级后文件仍保持旧内容，只追加本周摘要——这是预期行为，但浓缩失败没有任何警告日志提示，运维难以发现。

**建议修复**：截断后加提示，并增加失败日志级别：
```python
truncated = existing[:3000]  # 适当扩大
if len(existing) > 3000:
    truncated += "\n[...历史内容已截断...]"
# 降级时打印更明显的警告
print(f"  [skill_evolver] WARNING: {cat} 月度浓缩失败，已降级为追加模式 — {e}")
```

---

### HI-06 · `scripts/weekly_job.py:35-38` · 幂等检查使用 `today`（执行日期）而非 `week_label`，导致周报可重复生成

**问题**：幂等检查条件是 `report_date=? AND report_type='weekly'`，其中 `?` 绑定的是 `today`（如 `2026-06-08`）。如果周报在本周一生成失败后在本周二手动重跑，`today` 变成 `2026-06-09`，查询找不到周一的记录，**重复生成周报**并重复发送邮件。

**建议修复**：幂等键改用 `week_label`：
```python
if conn.execute(
    "SELECT 1 FROM reports WHERE report_date=? AND report_type='weekly'", (week_label,)
).fetchone():
```
并将 INSERT 语句的 `report_date` 字段也改为存 `week_label`（与查询一致）。

---

### HI-07 · `services/domestic_searcher.py:176` · `asyncio.run()` 在已有事件循环的环境中会抛出 RuntimeError

**问题**：`search_bilibili` 中调用 `asyncio.run(search.search_by_type(...))` 在 Python 3.10+ 中，如果在已有运行中事件循环的上下文（如 Jupyter、某些测试框架）被调用，会抛出 `RuntimeError: This event loop is already running`。虽然目前 bilibili 通道已从 `search_all_domestic` 调用链中移除，但函数仍存在于模块中，未来若重新启用会引入此问题。

**建议**：在函数内部处理事件循环：
```python
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(asyncio.run, search.search_by_type(...)).result()
    else:
        result = asyncio.run(search.search_by_type(...))
except Exception as e:
    ...
```

---

## MEDIUM（逻辑/健壮性问题，建议修复）

---

### ME-01 · `config.py:50-63` · `Config.validate()` 每次返回新 `Config()` 实例，配置验证与实际运行实例不一致

**问题**：`get_config()` 每次调用都 `return Config()`（第 67 行），创建一个新实例。`daily_job.py` 使用 `cfg = get_config()` 获取配置，但如果外部代码调用 `get_config().validate()` 来检查配置，它拿到的是另一个新实例，理论上在极端竞争条件下（如 `.env` 在两次调用间被修改）可能不一致。

**建议**：将 `Config` 改为模块级单例，或至少将 `validate()` 改为类方法：
```python
_config: Config | None = None
def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
```

---

### ME-02 · `services/layer2_filter.py:77-87` · `score_title` 仅对英文做 `.lower()` 但中文词汇大小写无关，且词汇匹配存在假阳性

**问题**：`t = title.lower()` 然后 `any(term.lower() in t for term in _CATEGORY_TERMS)` 做子串匹配。"防护" 出现在 `_CATEGORY_TERMS_DEFAULT` 中，会匹配"自我防护措施"、"防护林建设"等无关标题，给它们加 +2 分。噪音词 "招聘" 在词库里，但 "某科技公司招聘安全专员"（含 "安全"）会先得 +2 再得 -2，最终 score=0，依然通过 Layer2（默认阈值=1）。这是设计取舍，但 "防护" 这类高频泛义词是已知误判源，应记录为已知缺陷。

**建议**：将 "防护" 改为更具体的词组（"防护装备"、"个人防护"），或将 `LAYER2_MIN_SCORE` 提高到 2。

---

### ME-03 · `scripts/daily_job.py:104` · `db["version"]` 覆写为 ISO 周号字符串，破坏 `keyword_db.json` 原有版本格式

**问题**：`_update_keyword_hits` 将 `db["version"]` 设为 `"2026-W23"` 格式（第 104 行），而 `keyword_evolver.apply_evolution` 也做同样覆写（第 150 行），但两者每次调用都会触发，**每日日报也会更新 version 字段**。这意味着 `keyword_db.json` 的 version 字段每天都在变化，失去了版本管理的语义（只应在结构性变更时更新）。

**建议**：`version` 字段仅在 `apply_evolution`（周级进化）时更新，`_update_keyword_hits` 只更新 `last_updated`，不修改 `version`。

---

### ME-04 · `services/searcher.py:17-28` · `search_keyword` 无任何超时或重试，Tavily API 失败直接向上抛出

**问题**：`search_keyword` 中的 `client.search()` 没有设置超时（Tavily SDK 默认超时未知），也没有重试机制。在 `search_keywords` 的 for 循环中，单个关键词的 Tavily 失败会被捕获并打印，但如果 Tavily SDK 内部 hang 住（如 DNS 超时 120 秒），会阻塞整个日报流程。

**建议**：使用 `concurrent.futures.ThreadPoolExecutor` 或在调用 `TavilyClient` 时显式传递 timeout 参数（查阅 SDK 文档），或在 `search_keywords` 层加 `signal.alarm` 超时保护。

---

### ME-05 · `services/skill_evolver.py:92-152` · `evolve_analyzer_prompt` 将 LLM 建议直接写入文件，无内容长度或内容合规检查

**问题**：第 143 行将 `raw`（DeepSeek 原始返回）直接写入 `.md` 文件，未检查 `raw` 长度（如果 LLM 返回超长内容会写入大文件），也未检查内容是否包含有害字符。虽然这个文件只是提案，不自动生效，风险较低，但是写入前至少应做长度限制。

**建议**：`raw = raw[:3000]` 做截断保护。

---

### ME-06 · `services/keyword_evolver.py:79-152` · `apply_evolution` 进化日志 `reason` 字段在同时有退休和新增词时只记录退休原因

**问题**：第 141-146 行，`reason` 字段的逻辑是：如果 `retired` 非空则写退休原因，否则写 `"auto_new_word"`。但同一次进化可能同时有退休词和新增词，此时 `reason` 只记录退休原因，丢失了新增词的来源信息。

**建议**：
```python
"reason": ", ".join(filter(None, [
    f"yield_rate < {_MIN_YIELD_RATE} 连续 {_RETIRE_AFTER_WEEKS} 周" if retired else "",
    "auto_new_word" if added else "",
]))
```

---

### ME-07 · `scripts/weekly_job.py:91` · `kw_health_data` 传入全量 stats，日报只展示 Top 15，周报无此限制，可能生成极大 HTML

**问题**：`daily_job.py` 第 200-203 行对 `kw_health_data` 做了 `[:15]` 截断，而 `weekly_job.py` 第 91 行 `kw_health_data = {word: s for word, s in stats.items()}` 将全量关键词统计传入，最终由 `role_reporter._keyword_section` 在第 189 行 `sorted_kws[:20]` 截断。如果关键词库增长到几百个，`stats` 中会有大量数据在构建 dict 时完全展开，但因为有 `[:20]` 截断，实际展示没问题。风险是次要的，但语义不一致（日报显示 Top 15，周报显示 Top 20）。

**建议**：统一截断逻辑，明确在传入前 slice，而不是依赖 `_keyword_section` 内部的 `[:20]`。

---

## LOW（代码质量/一致性问题）

---

### LO-01 · `services/reporter.py` 整个文件 · `build_daily_html` / `build_weekly_html` 是孤儿函数，无任何外部调用

**问题**：`reporter.py` 文件中的两个核心函数已被 `role_reporter.py` 中的 `build_unified_html` 完全取代，但旧文件仍在。`daily_job.py` 现在 import 的是 `role_reporter.build_unified_html`，`reporter.py` 中的函数在整个代码库中无任何 import 引用。

**建议**：确认 `reporter.py` 确实无其他调用后，整体删除或归档，避免维护两套 HTML 模板逻辑产生混乱。

---

### LO-02 · `services/domestic_searcher.py:109-115` · 知乎 `items_raw` 变量被赋值后从未使用

**问题**：第 109-115 行将知乎 entities/answers 数据赋值给 `items_raw`，但后续代码（第 127 行）实际迭代的是 `search_result`，`items_raw` 从未被读取。这是死代码，且暗示了一段未完成的解析逻辑。

**建议**：删除 `items_raw` 赋值，或补充使用逻辑（如作为 fallback）。

---

### LO-03 · `services/analyzer.py:66` · `_SYSTEM_PROMPT` 为模块级变量，`analyzer.py` 被多处 import 但 prompt 只在进程启动时加载一次

**问题**：当用户在运行中更新了 `skills/analyzer_prompt/v2.md` 并希望立即生效时，由于模块级缓存，需要重启整个 Python 进程（cron 每次都是新进程，无影响）。但在开发调试场景下，同一进程内的多次调用不会 reload，可能导致困惑。这是已知的设计取舍（CLAUDE.md 注释也说明"每个进程只读一次文件"），记录此处仅作提醒。

---

### LO-04 · `scripts/daily_job.py:103` · 函数体内 `from datetime import date as _date`

**问题**：在 `_update_keyword_hits` 函数第 103 行有 `from datetime import date as _date`，但文件顶部已导入 `from datetime import datetime, timedelta`。完全可以用 `datetime.now().strftime("%G-W%V")` 替代，不需要额外 import。

**建议**：删除函数内 import，改用 `datetime.now().strftime("%G-W%V")`。

---

### LO-05 · `services/role_reporter.py:113` · 代码注释 "改动点 1" 等系列注释属于开发过程痕迹，应清理

**问题**：`role_reporter.py` 中多处注释如 "改动点 1：纵向排列的角色卡"（第 112 行）、"改动点 2"（第 297 行）、"改动点 3-6" 等，是重构过程的临时标注，不应保留在生产代码中，降低了代码可读性。

**建议**：删除所有"改动点 N"注释，保留必要的功能说明注释。

---

### LO-06 · `services/mailer.py:58` · 使用 `msg.as_string()` 而非 `msg.as_bytes()`

**问题**：`server.sendmail(cfg.SMTP_USER, recipients, msg.as_string())` 在邮件含非 ASCII 字符（中文主题、中文正文）时，`as_string()` 返回 str，smtplib 会将其编码为 ASCII，对于非 ASCII 字符会触发编码错误或乱码。正确做法是使用 `msg.as_bytes()` 或使用更现代的 `server.send_message(msg)` 方法（内部处理编码）。

**建议**：
```python
server.send_message(msg)  # 替代 server.sendmail(...)
```

---

### LO-07 · `services/searcher.py:52` · `urlparse(url).netloc.lstrip("www.")` 对多级域名行为错误

**问题**：`.lstrip("www.")` 不是前缀匹配，而是字符集删除。对于 `www.baidu.com` 会正确得到 `baidu.com`，但对于 `www2.example.com` 会错误得到 `2.example.com`（lstrip 删除所有出现在字符集 `{w, .}` 中的前导字符）。这是一个已知的 Python 陷阱。

**建议**：
```python
netloc = urlparse(url).netloc
source_name = netloc[4:] if netloc.startswith("www.") else netloc
```

---

### LO-08 · `scripts/seed_job.py:117-119` · seed 任务的 Layer3 上限使用 `LAYER3_CAP_TAVILY`，而非专用配置

**问题**：注释写 "seed 保守取 Tavily 桶上限"，直接复用 `cfg.LAYER3_CAP_TAVILY`（默认 15）。seed 任务是一次性历史回溯，理论上应处理更多条目，复用日报参数限制了 seed 的召回率。

**建议**：为 seed 任务增加独立配置 `SEED_LAYER3_CAP`（默认可设为 50），与日报参数解耦。

---

## 总分摘要

| 严重级别 | 数量 | 状态 |
|----------|------|------|
| CRITICAL | 5    | 必须修复后上线 |
| HIGH     | 7    | 应在近期 Sprint 修复 |
| MEDIUM   | 7    | 建议修复，降低运营风险 |
| LOW      | 8    | 代码卫生，建议清理 |
| **合计** | **27** | |

### 优先处理顺序

1. **CR-04（XSS）** — LLM/爬虫内容未转义直接写入 HTML，邮件客户端有执行风险，立即修复。
2. **CR-05 + CR-01（连接泄漏）** — cron 每日触发，连接未受 finally 保护，磁盘满等边界条件下会留下锁，导致次日任务无法运行。
3. **HI-06（周报幂等 bug）** — 已经在生产运行中，若周报某天失败后第二天重跑会重复发邮件。
4. **CR-02（事务一致性）** — 数据写入异常可能导致部分提交，影响数据完整性。
5. **HI-01（keyword_db.json 原子写）** — 词库文件损坏无法自动恢复，应优先处理。
6. **LO-06（mailer 中文编码）** — 邮件主题含中文，存在乱码风险，低成本修复。

---

## 补充 Bug 报告（2026-06-08 实测发现）

> 来源：手动触发 daily_job.py 后通过邮件报告 + DB 核查发现的运行时问题
> 经 DB 查询（`data/ciosh_intel.db`）与 HTML 报告交叉验证确认

---

### SUP-01 · `daily_job.py:41-57` · Layer1 批内同 URL 去重缺失，导致同一文章在报告中重复出现 N 次

**严重级别**：HIGH

**问题**：`_layer1_dedup()` 通过 `SELECT 1 FROM seen_urls WHERE url_hash=?` 检测已见 URL，但该检查只对比数据库里**已有的**历史记录，不感知**当前批次内部**的重复。当同一 URL 被多个不同关键词同时搜到时（例如今日的 indexbox.io Baltic 工业安全报告被 9 个关键词各自返回），9 个实例全部通过 `SELECT` 检查，全部进入 `new_items`，最终被 DeepSeek 分析 9 次并在 HTML 中出现 9 次。`executemany INSERT OR IGNORE` 只阻止了重复写入 `seen_urls`，但 `new_items` 里的 9 个副本已不可撤回。

**实测证据**：`indexbox.io/store/baltics-industrial-safety-controllers...` 在今日生成的 HTML 中出现 **9 次**，在 `intel_items` 表中只有 **1 条**（`URL UNIQUE` 约束生效，但 8 次浪费了 DeepSeek token）。

**建议修复**（最小改动，在 `_layer1_dedup` 内添加批内去重集合）：
```python
def _layer1_dedup(items, conn):
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    new_items, to_insert = [], []
    seen_in_batch = set()          # ← 新增：批内去重
    for item in items:
        url = item.get("url", "")
        h = hashlib.md5(url.encode()).hexdigest()
        if h in seen_in_batch:     # ← 批内重复直接跳过
            continue
        if conn.execute("SELECT 1 FROM seen_urls WHERE url_hash=?", (h,)).fetchone():
            continue
        new_items.append(item)
        to_insert.append((h, url, now))
        seen_in_batch.add(h)       # ← 标记已处理
    conn.executemany(
        "INSERT OR IGNORE INTO seen_urls(url_hash,url,first_seen) VALUES(?,?,?)",
        to_insert,
    )
    conn.commit()
    return new_items, len(items) - len(new_items)
```

---

### SUP-02 · `services/searcher.py:17-28` · Tavily `pub_date` 不过滤，老旧文章（2024/2025年）混入日报

**严重级别**：MEDIUM

**问题**：`search_keyword()` 传给 Tavily 的 `days=days_back`（默认 1）是**建议性参数**，Tavily 并不保证严格排除时间窗口外的内容——它返回的是"相关性最高的近期结果"，若某篇 2025 年文章在今日关键词下仍排名靠前，会被正常返回。`pub_date` 字段保存的是**原始发布时间**，不是抓取时间，且在 Layer2/Layer3 中无任何日期过滤。

**实测证据**：用户报告日报中出现 `https://news.sina.com.cn/sx/2025-04-03/detail-inerwmtr2617686.shtml`（2025-04-03 发布）。今日 DB 中该 URL 若存在则是因为 Tavily 按相关性排名将其返回，系统无任何机制拒绝。

**建议修复**（在 `daily_job.py` Step 2 后添加 pub_date 过滤，不改动 searcher.py 接口）：
```python
# Step 2.5: 过滤 pub_date 超出容忍范围的条目（可配置，默认容忍 7 天前）
MAX_PUB_AGE_DAYS = 7
cutoff = (datetime.now() - timedelta(days=MAX_PUB_AGE_DAYS)).strftime("%Y-%m-%d")

def _parse_pub_date(s: str) -> str:
    """尽力解析 pub_date 为 YYYY-MM-DD，解析失败返回空串。"""
    for fmt in ("%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt)+5].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""

before_date_filter = len(raw_results)
raw_results = [
    r for r in raw_results
    if not r.get("pub_date") or _parse_pub_date(r["pub_date"]) >= cutoff or _parse_pub_date(r["pub_date"]) == ""
]
print(f"  pub_date 过滤：丢弃 {before_date_filter - len(raw_results)} 条超龄文章")
```
> 注：`pub_date` 为空时保留（百度新闻不返回发布时间），只过滤有明确旧日期的条目。

---

### SUP-03 · `daily_job.py:141-172` · Part B 高/中重复同源（SUP-01 的衍生症状）

**严重级别**：INFO（根因是 SUP-01）

**问题**：同一 URL 被多个关键词搜到 → 多个实例进入 `analyzed` → DeepSeek 对同一内容独立分析，可能给出不同 `priority`（例如一次判 high、一次判 medium）→ 同一文章同时出现在 B-高优先级区块和 B-中优先级区块，造成"中高优先级情报完全重复"的视觉效果。

**根因**：与 SUP-01 完全相同，无需独立修复。修复 SUP-01 后此问题自动消失。

---

### SUP-04 · `daily_job.py:196-205` · Part D「总命中数」展示的是 API 搜索上限而非有效命中

**严重级别**：LOW

**问题**：`kw_health_data` 的 `total` 字段来自 `results_by_kw`，计算时机是 Layer1 去重**之前**（`raw_results = tavily_results + domestic_results`）。由于 Tavily 固定返回 `MAX_RESULTS_PER_KEYWORD=5` 条、百度固定返回 `max_results_each=3` 条，绝大多数关键词在 `results_by_kw` 中的值固定为 **8**，与该关键词当天是否产出高质量情报无关。Part D 展示的"总命中8"是**搜索 API 配额上限**，不是该词今日实际有价值命中数，用户无法从中判断关键词效果。

**实测证据**：今日 Part D 报告中所有热词总命中均为 8（用户反馈），而 `intel_items` 同词段条目数为 2-5（Layer1/2/3 过滤后），证明 8 是搜索上限而非有效命中。

**建议修复**：将 `kw_health_data` 的 `total` 改为 Layer2 通过数（已有相关性）或 Layer3 分析数（实际写入 DB 数），而非 Layer1 前的原始搜索结果数：
```python
# 当前：total = raw_results 中该词的数量（上限 = API cap）
# 建议：total = Layer3 分析后 analyzed 中该词的数量（反映真实有效命中）
quality_analyzed_by_kw: dict[str, int] = {}
total_analyzed_by_kw: dict[str, int] = {}
for item in analyzed:
    kw = item.get("source_keyword", "")
    total_analyzed_by_kw[kw] = total_analyzed_by_kw.get(kw, 0) + 1
    if (item.get("priority") or "").lower() in ("high", "medium"):
        quality_analyzed_by_kw[kw] = quality_analyzed_by_kw.get(kw, 0) + 1

kw_health_data = {
    word: {
        "total": total_analyzed_by_kw.get(word, 0),
        "quality": quality_analyzed_by_kw.get(word, 0),
        "yield_rate": ...,
    }
    for word in sorted(total_analyzed_by_kw, key=lambda w: total_analyzed_by_kw[w], reverse=True)[:15]
}
```

---

## 更新后总计

| 级别 | 原有 | 补充 | 合计 |
|----------|------|------|------|
| CRITICAL | 5    | 0    | 5    |
| HIGH     | 7    | 1    | 8    |
| MEDIUM   | 7    | 1    | 8    |
| LOW      | 8    | 1    | 9    |
| INFO     | 0    | 1    | 1    |
| **合计** | **27** | **3（+1 INFO）** | **31** |

---

*本报告由对抗性代码审计流程生成 · 补充 Bug 经实测验证 · 仅供内部参考*
