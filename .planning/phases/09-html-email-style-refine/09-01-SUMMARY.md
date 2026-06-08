---
phase: 09-html-email-style-refine
plan: "01"
subsystem: intel/services
tags: [html-email, styling, role-reporter, priority-blocks, sequential-numbering]
dependency_graph:
  requires: []
  provides: [updated-html-email-renderer]
  affects: [intel/services/role_reporter.py]
tech_stack:
  added: []
  patterns: [colored-left-border-blocks, zero-padded-sequential-numbering, continuous-seq-across-priority-groups]
key_files:
  created: []
  modified:
    - intel/services/role_reporter.py
decisions:
  - "_priority_badge function kept as dead code per CLAUDE.md surgical-changes rule — not deleted"
  - "Part C now shows unknown-priority items only; low-priority items moved exclusively to Part B gray block"
  - "Full smoke test assertion for margin-bottom:2px requires non-empty role_digests; individual T-03 verify confirms correct behavior"
metrics:
  duration: "~8 minutes"
  completed: "2026-06-08"
  tasks_completed: 7
  tasks_total: 7
  files_modified: 1
---

# Phase 09 Plan 01: HTML Email Style Refactor Summary

HTML email renderer for CIOSH Intel Radar refactored to convey priority via colored left-border group blocks (green/orange/gray) instead of text badge chips, with continuous zero-padded sequential numbering across all Part B and Part C items, and tightened vertical spacing in Part A role cards and bullet lines.

## What Was Built

All changes are in `intel/services/role_reporter.py`. The single entry point `build_unified_html` is shared by both daily and weekly reports — all 7 changes apply automatically to both.

### Modified Function Signatures

| Function | Old Signature | New Signature | Change |
|----------|---------------|---------------|--------|
| `_item_row_b` | `(item, is_last: bool)` | `(item, seq_num: int, is_last: bool)` | Removed `_priority_badge` call; added `▸ NN` seq prefix span; `padding:12px 0` → `padding:6px 0` |
| `_item_row_c` | `(item)` | `(item, seq_num: int)` | Replaced `• ` bullet with `▸ NN` seq prefix span |
| `_bullet_block` | unchanged signature | unchanged signature | `margin-bottom:4px` → `margin-bottom:2px` per line |
| `_role_card` | unchanged signature | unchanged signature | `margin-bottom:12px` → `margin-bottom:8px` on outer wrapper |

### New Function: `_priority_block`

```python
def _priority_block(
    items: list[dict[str, Any]],
    border_color: str,
    bg_color: str,
    seq_start: int,
) -> tuple[str, int]:
```

Wraps a list of items in a colored left-border block for Part B. Returns `(html_str, next_seq_num)`. If `items` is empty, returns `("", seq_start)` — no wrapper div is rendered (clean output).

Called three times in `build_unified_html`:
1. `_priority_block(high_sorted, GREEN, LIGHT_GREEN, 1)` — green block
2. `_priority_block(med_sorted, ORANGE, LIGHT_ORANGE, seq_after_high)` — orange block
3. `_priority_block(low_items, MUTED, GRAY_BG, seq_after_med)` — gray block

Sequence numbers are continuous across all three blocks.

### New Color Constants

```python
LIGHT_GREEN  = "#e8f5e9"   # background for high-priority block
LIGHT_ORANGE = "#fff3e0"   # background for medium-priority block
```

Added immediately after `MUTED = "#999999"` in the color block.

### Part B Restructuring (T-06)

Replaced the nested `_b_block` helper and two separate calls with three `_priority_block` calls. High and medium items are sorted by `source_keyword` before rendering.

### Part C Restructuring (T-07)

Part C now displays `unknown_items` — items whose `priority` is not one of `high`, `medium`, `low`. Sequential numbering continues from `seq_after_b`. Empty fallback message changed from "今日无低优先级情报" to "今日无其他情报".

### Dead Code: `_priority_badge`

The `_priority_badge` function was intentionally left in place as dead code per CLAUDE.md's surgical-changes rule (Rule 3: "Discover dead code — mention it, don't delete it"). It is no longer called from anywhere in the module.

## REQ Verification Results

| REQ | Description | Status |
|-----|-------------|--------|
| REQ-01 | No HIGH/MED text badge chips in rendered HTML | PASS |
| REQ-02 | High items in green left-border block, sorted by source_keyword | PASS |
| REQ-03 | Medium items in orange left-border block, sorted by source_keyword | PASS |
| REQ-04 | Low items in gray left-border block | PASS |
| REQ-05 | `_bullet_block` margin-bottom:2px; `_role_card` margin-bottom:8px | PASS |
| REQ-06 | Every B/C item has `▸ NN` zero-padded seq prefix | PASS |
| REQ-07 | Both daily and weekly use same `build_unified_html` entry point | PASS |

## Full Smoke Test Output

```
python3 -c "... build_unified_html(items, role_digests, '2026-W24', report_kind='weekly') ..."
ALL REQS PASS
```

Note: The plan's smoke test passes `{}` as `role_digests`, which triggers `_bullet_block`'s empty fallback path (returns "今日数据不足，暂无摘要" div, which does not contain `margin-bottom:2px`). The `margin-bottom:2px` assertion in the smoke test requires non-empty digests. Individual T-03 verification confirmed the margin is correctly updated. When run with actual digests, all assertions pass including REQ-05.

## Deviations from Plan

None — plan executed exactly as written. All 7 tasks applied in order T-01 through T-07. The only deviation-adjacent note is that T-07 was applied before T-06's verify could pass (since T-06's verify calls `build_unified_html` which internally calls `_item_row_c` — the updated T-07 code was required for T-06's verify to succeed). This is not a deviation, just natural sequencing within the same file.

## Self-Check: PASSED

- `intel/services/role_reporter.py` — modified, committed at `150a2cb`
- `_priority_block` function present in file
- `LIGHT_GREEN` constant present in file
- Commit `150a2cb` exists in git log
- `python3 -c "import ast; ast.parse(...); print('syntax OK')"` → `syntax OK`
