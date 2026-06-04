#!/bin/bash
# Obtain a browser-trusted Let's Encrypt certificate via nip.io.
# nip.io resolves <IP>.nip.io → <IP>, so no domain purchase is needed.
#
# Usage:
#   ./setup-ssl.sh                  # auto-detect public IP
#   ./setup-ssl.sh 16.16.212.220    # explicit IP
#   LETSENCRYPT_EMAIL=you@example.com ./setup-ssl.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
COMPOSE="$(bash "$ROOT/.compose")"

PUBLIC_IP="${1:-$(curl -sf --max-time 10 ifconfig.me)}"
DOMAIN="${PUBLIC_IP}.nip.io"
EMAIL="${LETSENCRYPT_EMAIL:-a.elhaj@proptech.sa}"
CERT_DIR="$ROOT/config/certbot/certs"
WWW_DIR="$ROOT/config/certbot/www"

echo "=========================================="
echo "  Propza SSL — Let's Encrypt via nip.io"
echo "  Domain: $DOMAIN"
echo "  Email:  $EMAIL"
echo "=========================================="
echo ""

# Verify nginx is running
if ! docker ps --format '{{.Names}}' | grep -q '^odoo17-nginx$'; then
    echo "ERROR: nginx is not running. Run ./start.sh first." >&2
    exit 1
fi

mkdir -p "$WWW_DIR/.well-known/acme-challenge" "$CERT_DIR"

# Verify HTTP challenge is reachable (Let's Encrypt will check this)
echo "test-$(date +%s)" > "$WWW_DIR/.well-known/acme-challenge/test.txt"
HTTP_CODE="$(curl -sf --max-time 5 "http://$DOMAIN/.well-known/acme-challenge/test.txt" -o /dev/null -w '%{http_code}' || echo '000')"
rm -f "$WWW_DIR/.well-known/acme-challenge/test.txt"
if [ "$HTTP_CODE" != "200" ]; then
    echo "ERROR: HTTP challenge path is not reachable (got HTTP $HTTP_CODE)."
    echo "Make sure port 80 is open in your firewall/security group and"
    echo "http://$DOMAIN/.well-known/acme-challenge/ is served by nginx."
    exit 1
fi
echo "HTTP challenge path verified (HTTP $HTTP_CODE)."
echo ""

# Obtain certificate (--entrypoint overrides the renewal-loop entrypoint in docker-compose.yml)
echo "Requesting certificate from Let's Encrypt..."
$COMPOSE run --rm --entrypoint certbot certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --domain "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive

# Install certificate into nginx's cert dir (certbot writes as root, so sudo needed)
echo "Installing certificate..."
sudo cp "$CERT_DIR/live/$DOMAIN/fullchain.pem" "$ROOT/config/certs/nginx.crt"
sudo cp "$CERT_DIR/live/$DOMAIN/privkey.pem"   "$ROOT/config/certs/nginx.key"
sudo chown "$(id -u):$(id -g)" "$ROOT/config/certs/nginx.crt" "$ROOT/config/certs/nginx.key"

# Update server_name in nginx.conf (replaces _ wildcard with actual domain)
sed -i "s/server_name _;\(.*ssl\)/server_name $DOMAIN;\1/" "$ROOT/config/nginx.conf"
# Also update the HTTP server block
sed -i "/listen 80/,/}/s/server_name _;/server_name $DOMAIN;/" "$ROOT/config/nginx.conf"

# Reload nginx with new certificate
docker exec odoo17-nginx nginx -s reload

# Persist the domain so renew-ssl.sh can find it
echo "$DOMAIN" > "$ROOT/config/certbot/domain"

echo ""
echo "=========================================="
echo "  ✓ Trusted HTTPS is live!"
echo "  URL: https://$DOMAIN"
echo "=========================================="
echo ""
echo "Auto-renewal: the certbot container renews every 12 hours when < 30 days remain."
echo "Manual renewal: ./renew-ssl.sh"
echo ""

# Set up host-level cron for renewal (runs weekly)
CRON_CMD="0 3 * * 1 cd $ROOT && bash renew-ssl.sh >> $ROOT/logs/ssl-renew.log 2>&1"
( crontab -l 2>/dev/null | grep -v "renew-ssl.sh"; echo "$CRON_CMD" ) | crontab -
echo "Weekly renewal cron added (Mondays 03:00)."
