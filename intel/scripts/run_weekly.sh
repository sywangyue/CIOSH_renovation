#!/bin/bash
# CIOSH Intel Radar — weekly job wrapper
# Cron: 30 19 * * 0 (UTC Sun 19:30 = Beijing Mon 03:30)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 等待外置盘挂载就绪
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

echo "[$(date '+%Y-%m-%d %H:%M:%S')] weekly_job starting"
"$PYTHON" scripts/weekly_job.py
EXIT_CODE=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] weekly_job done (exit $EXIT_CODE)"
