# CIOSH Intel Radar — Roadmap

## Phase 9: HTML Email Style Refinement
**Status:** planning
**Slug:** html-email-style-refine
**Goal:** 日报/周报 HTML 邮件样式微调：优先级分组色框 + A/B 紧凑布局序列号

### Requirements
- REQ-01: 移除所有 high / medium 文字标识（badge/chip）
- REQ-02: high 优先级条目按 source_keyword 排序，以绿色边框 block 集中展示
- REQ-03: medium 优先级条目按 source_keyword 排序，以橙色边框 block 集中展示
- REQ-04: 其他（low/unknown）条目以灰色边框 block 展示
- REQ-05: A/B 部分采用紧凑布局（减少每条垂直间距）
- REQ-06: A/B 每条前加统一序列号（非 1234 / abcd，可用自定义符号）
- REQ-07: 日报与周报共用同一 build_unified_html 模板，改动必须对两者生效
