#!/bin/bash
# Create the demodb database and install all Propza custom addons.
#
# Usage:
#   ./create-demodb.sh              Create demodb + install + configure
#   ./create-demodb.sh --upgrade    Re-upgrade all modules on existing demodb
#
# After this, optionally run:
#   ./create-demo-data.sh           Load Arabic demo data

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DB="${ODOO_DB:-demodb}"

require_containers() {
    if ! docker ps --format '{{.Names}}' | grep -q '^odoo17$'; then
        echo "ERROR: Odoo is not running. Start it first: ./start.sh" >&2
        exit 1
    fi
}

db_exists() {
    docker exec odoo17-db psql -U odoo17 -d postgres -lqt 2>/dev/null \
        | cut -d'|' -f1 | tr -d ' ' | grep -qx "$1"
}

UPGRADE=false
for arg in "$@"; do
    case "$arg" in
        -u|--upgrade) UPGRADE=true ;;
        -h|--help)
            head -12 "$0" | tail -n +2 | sed 's/^# \{0,1\}//'
            exit 0
            ;;
    esac
done

require_containers

echo "=========================================="
echo "  Create Propza database: $DB"
echo "=========================================="
echo ""

if db_exists "$DB"; then
  if [ "$UPGRADE" = true ]; then
    echo "Database '$DB' exists — upgrading modules..."
    exec "$ROOT/install-addons.sh" -u --configure "$DB"
  fi
  echo "Database '$DB' already exists."
  echo "  ./install-addons.sh -u --configure $DB   Upgrade all modules"
  echo "  ./create-demo-data.sh                    Optional demo data (not required)"
  exit 0
fi

echo "Creating '$DB' and installing all custom addons (~5 minutes)..."
echo ""

exec "$ROOT/install-addons.sh" --configure "$DB"
