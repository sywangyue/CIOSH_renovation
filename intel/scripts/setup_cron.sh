#!/bin/bash
# 自动写入 crontab（幂等：已存在则跳过）
# 运行：bash scripts/setup_cron.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MARKER="# CIOSH Intel Radar"
EXISTING=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING" | grep -qF "$MARKER"; then
    echo "crontab 已包含 CIOSH Intel Radar 条目，跳过写入。"
else
    (echo "$EXISTING"; \
     echo ""; \
     echo "$MARKER"; \
     echo "0 19 * * * \"$PROJECT_DIR/scripts/run_daily.sh\" >> \"$PROJECT_DIR/logs/cron_daily.log\" 2>&1"; \
     echo "30 19 * * 0 \"$PROJECT_DIR/scripts/run_weekly.sh\" >> \"$PROJECT_DIR/logs/cron_weekly.log\" 2>&1") \
    | crontab -
    echo "已写入 crontab。"
fi

echo ""
echo "当前 crontab 内容："
crontab -l
echo ""
echo "时区说明：cron 使用 UTC。北京时间 03:00 = UTC 19:00（前一历日）"
echo "          周报在北京时间周一 03:30 执行"
