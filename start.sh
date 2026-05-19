#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$(bash "$ROOT/.compose")"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/odoo.log"

cd "$ROOT"
mkdir -p "$LOG_DIR" config
# Odoo runs as uid 101 inside the container; allow it to create logs/odoo.log.
chmod 777 "$LOG_DIR"
rm -f "$LOG_FILE"

echo "=========================================="
echo "    Starting Odoo 17 (propza-amlak)"
echo "=========================================="
echo ""
echo "Addons: $ROOT/addons -> /mnt/extra-addons"
echo "Logs:   $LOG_FILE"
echo ""

if docker ps --format '{{.Names}}' | grep -q '^odoo17$'; then
    echo "Odoo is already running."
    echo "  ./stop.sh    - stop containers"
    echo "  ./logs.sh    - follow logs"
    exit 0
fi

echo "Starting containers..."
$COMPOSE up -d

echo ""
echo "Waiting for database..."
for _ in $(seq 1 30); do
    if docker exec odoo17-db pg_isready -U odoo17 > /dev/null 2>&1; then
        echo "Database ready."
        break
    fi
    sleep 2
    echo -n "."
done
echo ""

for _ in $(seq 1 30); do
    if docker ps --format '{{.Names}}' | grep -q '^odoo17$'; then
        break
    fi
    sleep 2
done

if docker ps --format '{{.Names}}' | grep -q '^odoo17$'; then
    echo ""
    echo "Odoo 17 is running."
    echo "  URL:    http://localhost:8069"
    echo "  Logs:   ./logs.sh  (or tail -f logs/odoo.log)"
    echo "  Stop:   ./stop.sh"
    echo ""
else
    echo "Failed to start. Check: $COMPOSE logs web"
    exit 1
fi
