#!/usr/bin/env bash
# Starts SA Economy Pulse: waits for Docker, starts Postgres, then runs Dagster in the
# foreground. Windows Task Scheduler calls this through wsl.exe; keeping Dagster in the
# foreground keeps WSL (and so Dagster) alive until the stop task ends it.
set -euo pipefail

PROJECT="$HOME/sa-economy-pulse"
cd "$PROJECT"
mkdir -p logs
exec > >(tee -a logs/pipeline.log) 2>&1
echo "=== $(date '+%F %T') starting"

# Only run in the evening window (20:00 to 23:30), e.g. if the laptop is opened at 23:45
NOW=$(TZ=Africa/Johannesburg date +%H%M)
if [ "$NOW" -lt 2000 ] || [ "$NOW" -ge 2330 ]; then
    echo "Outside the 20:00-23:30 window ($NOW) - not starting"
    exit 0
fi

if pgrep -f "dagster dev" > /dev/null; then
    echo "Dagster is already running - nothing to do"
    exit 0
fi

# Docker Desktop can take a minute to start after sign-in: wait up to 5 minutes
for _ in $(seq 1 30); do
    docker info > /dev/null 2>&1 && break
    echo "waiting for Docker..."
    sleep 10
done
docker info > /dev/null 2>&1 || { echo "Docker never started - giving up"; exit 1; }

docker compose up -d

export DAGSTER_HOME="$PROJECT/.dagster"
source .venv/bin/activate
echo "starting Dagster at http://localhost:3000"
exec dagster dev -f orchestration/definitions.py
