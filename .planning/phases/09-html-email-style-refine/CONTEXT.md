# Phase 9 Context — HTML Email Style Refinement

## Goal
微调 CIOSH 情报雷达日报/周报的 HTML 邮件样式，使优先级信息通过颜色分组块而非文字标签传递，并让 A/B 部分更紧凑可读。

## Scope
- 修改文件：`intel/services/role_reporter.py`（唯一 HTML 生成入口）
- 日报和周报共用 `build_unified_html()`，改一处即全覆盖
- 不新增功能，不改变数据流，只改 HTML 渲染逻辑

## Requirements

| ID | Requirement |
|----|-------------|
| REQ-01 | 移除所有 high / medium 文字标识（badge/chip 样式的 "HIGH" "MEDIUM" 标签） |
| REQ-02 | high 优先级条目：按 source_keyword 字段排序，包裹在绿色左边框 block 内 |
| REQ-03 | medium 优先级条目：按 source_keyword 字段排序，包裹在橙色左边框 block 内 |
| REQ-04 | 其他条目（low/unknown）：包裹在灰色左边框 block 内 |
| REQ-05 | A/B 部分采用紧凑布局（减少 card 上下 padding，紧缩行距） |
| REQ-06 | A/B 每条前加统一序列符号（自定义，不用 1234/abcd） |
| REQ-07 | 改动对日报与周报均生效（通过共用模板自动满足） |

## Decisions

- D-01: 分组块采用左侧 4px 彩色 border + 浅色背景底色的卡片风格，不用全边框
- D-02: 序列号采用「▸」或「›」符号前缀，保持符合邮件客户端兼容性
- D-03: 分组排序键 = source_keyword（已有字段），组内保持原有 priority→collected_at 顺序
- D-04: 颜色参考 CIOSH 品牌色系（绿 #4CAF50 / 橙 #FF9800 / 灰 #9E9E9E），左边框加浅底色

## Key Files

```
intel/services/role_reporter.py   ← 主要修改目标，含 _item_row_b/_item_row_c/_role_card/build_unified_html
intel/services/reporter.py        ← 仅含 build_daily_html（Phase 7 遗留死代码），不触碰
```

## Constraints (from CLAUDE.md)
- 每次回答必须以 "Hello Max" 开头
- 外科手术式改动：只改需要改的，不重构周边代码
- 不引入新功能
- keyword_db.json 的修改必须原子写入（本 phase 不涉及）

## Current State
`role_reporter.py` 现有：
- `_item_row_b(item, show_priority)` — Part B 行渲染（含 priority badge HTML）
- `_item_row_c(item)` — Part C 行渲染
- `_role_card(items, role_label, ...)` — 组装单角色卡片
- `build_unified_html(items, role_digests, date_label, kw_health_data, retired, new_candidates, report_kind)` — 顶层入口

## Out of Scope
- C/D 部分样式（关键词健康度表格、进化摘要）保持不变
- 邮件发送逻辑（mailer.py）不动
- 移动端邮件客户端适配（超出当前 scope）
