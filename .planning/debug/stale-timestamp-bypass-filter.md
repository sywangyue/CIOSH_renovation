---
slug: stale-timestamp-bypass-filter
status: resolved
trigger: "信息源时间戳过旧的文章仍然出现在每日采集报告中。示例URL：https://yjgl.ganzhou.gov.cn/gzsyjgl/c103041/202410/c1d2753434164d0eae4ab0cadf3fca21.shtml（2024年10月文章）依然出现在2026-06-08的日报内。"
created: 2026-06-08
updated: 2026-06-08
---

## Symptoms

- **expected**: 日报只包含最近7天（MAX_PUB_AGE_DAYS=7）的新鲜内容
- **actual**: 2024年甚至更早的文章出现在当日日报中
- **example_url**: https://yjgl.ganzhou.gov.cn/gzsyjgl/c103041/202410/c1d2753434164d0eae4ab0cadf3fca21.shtml
- **example_date_in_url**: 202410（2024年10月）
- **timeline**: 今日（2026-06-08）跑完整采集后发现，Phase 8 已实现 _filter_by_pub_date 但问题仍存在
- **reproduction**: 运行 daily_job.py 后查看邮件报告，可见旧文章

## Current Focus

hypothesis: "_filter_by_pub_date 依赖 pub_date 字段过滤，但搜索源（Tavily/百度）返回的 pub_date 为空或不准确，导致旧文章因「无日期→保留」策略绕过过滤"
test: "查询今日 intel_items 中 pub_date 为空的条目比例，并检查其实际收录的文章日期"
expecting: "大量条目 pub_date='' 从而绕过 _filter_by_pub_date；或 pub_date 值不准确（如 Tavily 对政府网站返回错误日期）"
next_action: "已完成根因分析并修复"

## Evidence

- timestamp: 2026-06-08T22:00:00
  finding: "今日 DB 40条中 25条 pub_date=''，其中包括 ganzhou 2024年URL"
  source: "sqlite query on intel/data/ciosh_intel.db"

- timestamp: 2026-06-08T22:01:00
  finding: "domestic_searcher.py search_baidu() 第77行硬编码 pub_date: '' — 所有百度通道结果无日期"
  source: "intel/services/domestic_searcher.py line 77"

- timestamp: 2026-06-08T22:02:00
  finding: "Tavily 返回 RFC 822 格式日期（'Sun, 07 Jun 2026 22:11:35 GMT'），_filter_by_pub_date 只解析 ISO 8601，RFC 822 无法解析 → 判定为「无日期→保留」"
  source: "intel/scripts/daily_job.py _filter_by_pub_date line 130"

## Resolution

root_cause: "两个漏洞叠加：(A) 百度通道 pub_date 恒为空，旧文章无条件通过过滤；(B) Tavily 返回 RFC 822 日期格式，_filter_by_pub_date 只支持 ISO 8601，解析失败同样触发「无日期→保留」策略"
fix: "重构 _filter_by_pub_date 为两函数：_parse_pub_date（支持 ISO 8601 + RFC 822 + URL 路径 YYYYMM/YYYYMMDD 模式）+ _filter_by_pub_date（调用前者）。URL 路径回退逻辑在 pub_date='' 时从 URL 中提取日期，覆盖政府/新闻网站常见路径模式。"
files_changed:
  - intel/scripts/daily_job.py
