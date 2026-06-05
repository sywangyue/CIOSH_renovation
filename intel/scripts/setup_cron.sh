#!/bin/bash
# 打印需要添加到 crontab 的行（不自动修改 crontab，需用户确认后手动添加）
# 运行：bash scripts/setup_cron.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ""
echo "在终端运行 crontab -e，添加以下两行："
echo ""
echo "# CIOSH Intel Radar"
echo "0 19 * * * $PROJECT_DIR/scripts/run_daily.sh >> $PROJECT_DIR/logs/cron_daily.log 2>&1"
echo "30 19 * * 0 $PROJECT_DIR/scripts/run_weekly.sh >> $PROJECT_DIR/logs/cron_weekly.log 2>&1"
echo ""
echo "时区说明：cron 使用 UTC。北京时间 03:00 = UTC 19:00（前一历日）"
echo "          周报在北京时间周一 03:30 执行"
