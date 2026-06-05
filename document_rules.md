# document_rules — CIOSH 项目文件命名规范

## S-document（战略分析文档）

位置：`docs/`

格式：`YYYY-MM-DD_S[N]_[topic_en_lower_snake].md`

规则：
- S 编号从 S01 起，连续递增，不跳号
- 主题用英文小写 + underscore，不用 hyphen
- 同日多篇按产出顺序递增 S 编号

示例：
```
2026-04-24_S01_category_gap_map.md
2026-04-28_S02_poc_transformation_plan.md
2026-04-30_S03_laobao_cloud_audit.md
```

## Branding（品牌文件）

位置：`Branding/`

格式：`CIOSH_[descriptor].[ext]`

规则：
- 只用英文
- 前缀统一 `CIOSH_`
- descriptor 用 underscore 连接

示例：
```
CIOSH_2026_KV_horizontal.eps
CIOSH_mascot.ai
logo_header.png
```

## 数据文件

位置：`data/`

格式：`[name_en].[ext]` 或 `[name_cn].[ext]`

## 归档文件

位置：`archive/`

分类：
- `archive/scripts/` — 一次性脚本
- `archive/screenshots/YYYY-MM-DD_S[N]/` — 关联某 S-document 的截图

## 原则

- S-document 只记录当次讨论，不溯改，不追加
- S-document 之间不互相引用，独立成册
- 推断、计划、假设只进 S-document，不进 `Agent.md`
- 事实类由业主方决定回写到 `Agent.md`
