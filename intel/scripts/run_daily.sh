#!/bin/bash
# CIOSH Intel Radar — daily job wrapper
# Cron: 0 19 * * * (UTC 19:00 = Beijing 03:00 next day)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 等待外置盘挂载就绪（launchd 在 Mac 唤醒时可能抢在 APFS 卷就绪前触发）
WAIT=0
while [ ! -d "$PROJECT_DIR" ] && [ $WAIT -lt 30 ]; do
    sleep 2
    WAIT=$((WAIT + 2))
done
if [ ! -d "$PROJECT_DIR" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: PROJECT_DIR not available: $PROJECT_DIR"
    exit 1
fi

cd "$PROJECT_DIR"

if [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily_job starting"
"$PYTHON" scripts/daily_job.py
EXIT_CODE=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily_job done (exit $EXIT_CODE)"
