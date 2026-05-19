#!/bin/bash
# Install or upgrade all Propza custom Odoo addons on an existing database.
#
# Usage:
#   ./install-addons.sh [database]              Install modules (default DB: demodb)
#   ./install-addons.sh -u [database]           Upgrade modules
#   ./install-addons.sh --configure [database]  Install + set SAR / Saudi Arabia / Arabic
#   ./install-addons.sh --list                  Print discovered module names
#
# Examples:
#   ./install-addons.sh demodb
#   ./install-addons.sh -u demodb
#   ./install-addons.sh --configure demodb

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ADDONS_DIR="$ROOT/addons"
COMPOSE="$(bash "$ROOT/.compose")"
DB="${ODOO_DB:-demodb}"
MODE="install"
CONFIGURE=false
SKIP_RESTART=false
EXTRA_MODULES=""

usage() {
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
    echo ""
    echo "Environment:"
    echo "  ODOO_DB          Default database name (default: demodb)"
    echo "  ADMIN_EMAIL      Admin login when using --configure (default: admin@propza.sa)"
    echo "  ADMIN_PASSWORD   Admin password when using --configure (default: admin)"
}

discover_modules() {
    local mods=()
    local d name
    for d in "$ADDONS_DIR"/*/; do
        [ -d "$d" ] || continue
        [ -f "${d}__manifest__.py" ] || continue
        name="$(basename "$d")"
        mods+=("$name")
    done
    if [ "${#mods[@]}" -eq 0 ]; then
        echo "ERROR: No custom modules found in $ADDONS_DIR" >&2
        exit 1
    fi
    (IFS=','; echo "${mods[*]}")
}

db_exists() {
    docker exec odoo17-db psql -U odoo17 -d postgres -lqt 2>/dev/null \
        | cut -d'|' -f1 | tr -d ' ' | grep -qx "$1"
}

require_containers() {
    if ! docker ps --format '{{.Names}}' | grep -q '^odoo17$'; then
        echo "ERROR: Odoo is not running. Start it first: ./start.sh" >&2
        exit 1
    fi
}

configure_company() {
    local db="$1"
    local admin_email="${ADMIN_EMAIL:-admin@propza.sa}"
    local admin_password="${ADMIN_PASSWORD:-admin}"

    echo ""
    echo "Configuring company locale (SAR, Saudi Arabia, Arabic)..."

    $COMPOSE run --rm -T web odoo shell -d "$db" << PYEOF
SAR = env['res.currency'].search([('name', '=', 'SAR')], limit=1)
SA = env['res.country'].search([('code', '=', 'SA')], limit=1)
company = env.company

if SAR:
    SAR.active = True
    company.currency_id = SAR
if SA:
    company.country_id = SA
company.write({
    'name': company.name or 'Propza',
    'phone': company.phone or '+966000000000',
})

admin = env['res.users'].search([('login', '=', '${admin_email}')], limit=1)
if not admin:
    admin = env['res.users'].search([('id', '=', 2)], limit=1)
if admin:
    admin.write({
        'login': '${admin_email}',
        'email': '${admin_email}',
        'lang': 'ar_001',
        'tz': 'Asia/Riyadh',
        'password': '${admin_password}',
    })

env.cr.commit()
print('Company and admin configured.')
PYEOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        -u|--upgrade)
            MODE="upgrade"
            shift
            ;;
        --configure)
            CONFIGURE=true
            shift
            ;;
        --skip-restart)
            SKIP_RESTART=true
            shift
            ;;
        --list)
            discover_modules | tr ',' '\n'
            exit 0
            ;;
        --modules)
            EXTRA_MODULES="${2:-}"
            [ -n "$EXTRA_MODULES" ] || { echo "ERROR: --modules requires a value" >&2; exit 1; }
            shift 2
            ;;
        -*)
            echo "ERROR: Unknown option: $1" >&2
            usage
            exit 1
            ;;
        *)
            DB="$1"
            shift
            ;;
    esac
done

MODULES="${EXTRA_MODULES:-$(discover_modules)}"
MODULE_COUNT="$(echo "$MODULES" | tr ',' '\n' | wc -l)"

cd "$ROOT"
require_containers

echo "=========================================="
echo "  Propza custom addons — $MODE"
echo "=========================================="
echo "Database:  $DB"
echo "Modules:   $MODULE_COUNT addons"
echo "Addons:    $ADDONS_DIR"
echo ""

if ! db_exists "$DB"; then
    echo "Database '$DB' does not exist yet."
    echo "Odoo will create it during install (first run may take several minutes)."
    echo ""
fi

LOG_FILE="$ROOT/logs/install-${DB}-$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$ROOT/logs"

ACTION_FLAG="-i"
[ "$MODE" = "upgrade" ] && ACTION_FLAG="-u"

echo "Running odoo $ACTION_FLAG (logging to $LOG_FILE)..."
echo ""

set +e
$COMPOSE run --rm -T web odoo \
    -d "$DB" \
    --without-demo=all \
    --load-language ar_001 \
    "$ACTION_FLAG" "$MODULES" \
    --stop-after-init \
    2>&1 | tee "$LOG_FILE"
INSTALL_STATUS=${PIPESTATUS[0]}
set -e

if [ "$INSTALL_STATUS" -ne 0 ]; then
    echo ""
    echo "ERROR: Module $MODE failed. See $LOG_FILE"
    exit "$INSTALL_STATUS"
fi

if [ "$CONFIGURE" = true ]; then
    configure_company "$DB"
fi

if [ "$SKIP_RESTART" = false ]; then
    echo ""
    echo "Restarting Odoo web container..."
    $COMPOSE restart web
fi

echo ""
echo "Done. Modules ${MODE}ed on database '$DB'."
echo "  URL:      http://localhost:8069"
echo "  Log:      $LOG_FILE"
if [ "$CONFIGURE" = true ]; then
    echo "  Admin:    ${ADMIN_EMAIL:-admin@propza.sa} / ${ADMIN_PASSWORD:-admin}"
fi
echo ""
echo "Demo data is optional: ./create-demo-data.sh   (only if you want sample records)"
