#!/usr/bin/env bash
# Stops Dagster (and anything it started). Postgres keeps running - it's cheap and
# Docker Desktop stops it when Windows shuts down.
PROJECT="$HOME/sa-economy-pulse"
mkdir -p "$PROJECT/logs"
echo "=== $(date '+%F %T') stopping" >> "$PROJECT/logs/pipeline.log"
pkill -INT -f "dagster dev" || echo "Dagster was not running" >> "$PROJECT/logs/pipeline.log"
