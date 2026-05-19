#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$(bash "$ROOT/.compose")"

cd "$ROOT"

echo "Stopping Odoo 17..."
$COMPOSE down

echo ""
echo "Stopped."
echo "  Start again: ./start.sh"
echo "  Log file kept at: logs/odoo.log"
