#!/bin/bash
# ============================================================================
# Odoo 17 Docker bootstrap for propza-amlak
# Mounts ./addons into the container and creates start/stop/log scripts.
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
ADDONS_DIR="$PROJECT_DIR/addons"
CONFIG_DIR="$PROJECT_DIR/config"
LOG_DIR="$PROJECT_DIR/logs"
BACKUP_DIR="$PROJECT_DIR/backups"

MASTER_PASSWORD="${MASTER_PASSWORD:-admin@123}"
DB_USER="${DB_USER:-odoo17}"
DB_PASSWORD="${DB_PASSWORD:-odoo17}"
ODOO_PORT="${ODOO_PORT:-8069}"

detect_docker_compose() {
    if docker compose version &> /dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose &> /dev/null 2>&1; then
        echo "docker-compose"
    else
        echo ""
    fi
}

DOCKER_COMPOSE="$(detect_docker_compose)"

echo -e "${BLUE}========================================================"
echo "    Odoo 17 Docker Setup (propza-amlak)"
echo "========================================================${NC}"
echo ""

echo -e "${YELLOW}Checking prerequisites...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed.${NC}"
    exit 1
fi
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker is not running.${NC}"
    exit 1
fi
if [ -z "$DOCKER_COMPOSE" ]; then
    echo -e "${RED}Docker Compose is not installed.${NC}"
    exit 1
fi
echo -e "${GREEN}Docker OK (${DOCKER_COMPOSE})${NC}"
echo ""

if [ ! -d "$ADDONS_DIR" ]; then
    echo -e "${RED}Missing addons directory: $ADDONS_DIR${NC}"
    exit 1
fi

echo -e "${YELLOW}Project:${NC} $PROJECT_DIR"
echo -e "${YELLOW}Addons:${NC}  $ADDONS_DIR  ->  /mnt/extra-addons"
echo -e "${YELLOW}Port:${NC}    $ODOO_PORT"
echo ""

mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$BACKUP_DIR"
touch "$LOG_DIR/.gitkeep" "$BACKUP_DIR/.gitkeep"

# docker-compose.yml — bind repo ./addons
cat > "$PROJECT_DIR/docker-compose.yml" << 'DOCKERCOMPOSE'
services:
  db:
    image: postgres:15
    container_name: odoo17-db
    environment:
      - POSTGRES_USER=odoo17
      - POSTGRES_PASSWORD=odoo17
      - POSTGRES_DB=postgres
      - PGDATA=/var/lib/postgresql/data/pgdata
    volumes:
      - odoo-db-data:/var/lib/postgresql/data/pgdata
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo17"]
      interval: 5s
      timeout: 5s
      retries: 10

  web:
    image: odoo:17.0
    container_name: odoo17
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "8069:8069"
    environment:
      - HOST=db
      - USER=odoo17
      - PASSWORD=odoo17
    volumes:
      - odoo-web-data:/var/lib/odoo
      - ./config:/etc/odoo
      - ./addons:/mnt/extra-addons
      - ./logs:/var/log/odoo
    restart: unless-stopped

volumes:
  odoo-web-data:
    driver: local
  odoo-db-data:
    driver: local
DOCKERCOMPOSE

cat > "$CONFIG_DIR/odoo.conf" << ODOOCONF
[options]
admin_passwd = ${MASTER_PASSWORD}
db_host = db
db_port = 5432
db_user = ${DB_USER}
db_password = ${DB_PASSWORD}
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
data_dir = /var/lib/odoo
logfile = /var/log/odoo/odoo.log
log_level = info
workers = 0
max_cron_threads = 1
list_db = True
ODOOCONF

chmod 644 "$CONFIG_DIR/odoo.conf"
chmod +x "$PROJECT_DIR"/.compose "$PROJECT_DIR"/start.sh "$PROJECT_DIR"/stop.sh "$PROJECT_DIR"/logs.sh 2>/dev/null || true

if [ ! -f "$PROJECT_DIR/.gitignore" ]; then
    cat > "$PROJECT_DIR/.gitignore" << 'GITIGNORE'
logs/*.log
logs/odoo.log
backups/*.sql
backups/*.gz
__pycache__/
*.pyc
.env
GITIGNORE
fi

echo -e "${GREEN}Setup files written.${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  cd $PROJECT_DIR"
echo "  ./start.sh"
echo "  ./logs.sh"
echo ""
echo -e "${BLUE}Access:${NC} http://localhost:${ODOO_PORT}"
echo -e "${BLUE}Master password:${NC} ${MASTER_PASSWORD}"
echo ""

read -r -p "Start Odoo now? (yes/no): " start_now
if [ "$start_now" = "yes" ]; then
    exec "$PROJECT_DIR/start.sh"
fi
