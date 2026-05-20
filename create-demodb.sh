#!/bin/bash
# Create and configure a Propza database from scratch.
#
# Usage:
#   ./create-demodb.sh [database]                    Create + install + configure
#   ./create-demodb.sh -u  [database]                Upgrade all modules on existing DB
#   ./create-demodb.sh -f  [database]                Drop existing DB, recreate from scratch
#   ./create-demodb.sh --with-demo [database]        Create + install + load demo data
#   ./create-demodb.sh -f --with-demo [database]     Full clean setup with demo data
#
# Flags can be combined:  ./create-demodb.sh -f --with-demo propza
#
# Environment:
#   ODOO_DB   Default database name (default: demodb)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DB="${ODOO_DB:-demodb}"
UPGRADE=false
FRESH=false
WITH_DEMO=false

usage() {
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    echo ""
}

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

drop_db() {
    local db="$1"
    echo "Terminating open connections to '$db'..."
    docker exec odoo17-db psql -U odoo17 -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$db' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true
    echo "Dropping database '$db'..."
    docker exec odoo17-db psql -U odoo17 -d postgres -c "DROP DATABASE IF EXISTS \"$db\";"
    echo "Database '$db' dropped."
    echo ""
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)    usage; exit 0 ;;
        -u|--upgrade) UPGRADE=true; shift ;;
        -f|--fresh)   FRESH=true; shift ;;
        --with-demo)  WITH_DEMO=true; shift ;;
        -*)
            echo "ERROR: Unknown option: $1" >&2
            usage
            exit 1
            ;;
        *)
            DB="$1"; shift ;;
    esac
done

require_containers

echo "=========================================="
echo "  Propza database: $DB"
echo "=========================================="
echo ""

# Drop existing DB if --fresh requested
if [ "$FRESH" = true ] && db_exists "$DB"; then
    drop_db "$DB"
fi

# Upgrade path
if db_exists "$DB"; then
    if [ "$UPGRADE" = true ]; then
        echo "Database '$DB' exists — upgrading all modules..."
        ODOO_DB="$DB" "$ROOT/install-addons.sh" -u --configure "$DB"
        if [ "$WITH_DEMO" = true ]; then
            echo ""
            echo "Loading demo data..."
            ODOO_DB="$DB" "$ROOT/create-demo-data.sh"
        fi
        exit 0
    fi
    echo "Database '$DB' already exists."
    echo ""
    echo "Options:"
    echo "  -u  [db]           Upgrade all modules"
    echo "  -f  [db]           Drop and recreate from scratch"
    echo "  --with-demo [db]   Load demo data into existing DB"
    echo ""
    if [ "$WITH_DEMO" = true ]; then
        echo "Loading demo data into existing database..."
        ODOO_DB="$DB" "$ROOT/create-demo-data.sh"
    fi
    exit 0
fi

# Fresh install
echo "Creating '$DB' and installing all custom addons (~5 minutes)..."
echo ""

ODOO_DB="$DB" "$ROOT/install-addons.sh" --configure "$DB"
INSTALL_STATUS=$?

if [ "$INSTALL_STATUS" -ne 0 ]; then
    echo "ERROR: Install failed (exit $INSTALL_STATUS)." >&2
    exit "$INSTALL_STATUS"
fi

if [ "$WITH_DEMO" = true ]; then
    echo ""
    echo "=========================================="
    echo "  Loading demo data → $DB"
    echo "=========================================="
    echo ""
    ODOO_DB="$DB" "$ROOT/create-demo-data.sh"
fi

echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo "  URL:  http://localhost:8069"
echo "  DB:   $DB"
if [ "$WITH_DEMO" = true ]; then
    echo "  Demo users password: demo"
fi
echo ""
