#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$(bash "$ROOT/.compose")"
LOG_FILE="$ROOT/logs/odoo.log"

cd "$ROOT"

usage() {
    echo "Usage: ./logs.sh [file|docker|all]"
    echo "  file   - tail logs/odoo.log (default)"
    echo "  docker - docker compose logs for web service"
    echo "  all    - both file and container logs"
}

mode="${1:-file}"

case "$mode" in
    file)
        mkdir -p "$ROOT/logs"
        if [ ! -f "$LOG_FILE" ]; then
            echo "No log file yet. Start Odoo with ./start.sh"
            exit 1
        fi
        echo "Following $LOG_FILE (Ctrl+C to exit)"
        tail -f "$LOG_FILE"
        ;;
    docker)
        echo "Following container logs (Ctrl+C to exit)"
        $COMPOSE logs -f --tail=100 web
        ;;
    all)
        mkdir -p "$ROOT/logs"
        echo "Following file + container logs (Ctrl+C to exit)"
        tail -f "$LOG_FILE" &
        TAIL_PID=$!
        trap 'kill "$TAIL_PID" 2>/dev/null' EXIT INT TERM
        $COMPOSE logs -f --tail=50 web
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo "Unknown mode: $mode"
        usage
        exit 1
        ;;
esac
