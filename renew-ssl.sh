#!/bin/bash
# Renew Let's Encrypt certificate and reload nginx.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
COMPOSE="$(bash "$ROOT/.compose")"

DOMAIN_FILE="$ROOT/config/certbot/domain"
if [ ! -f "$DOMAIN_FILE" ]; then
    echo "No domain configured. Run ./setup-ssl.sh first." >&2
    exit 1
fi
DOMAIN="$(cat "$DOMAIN_FILE")"

echo "Renewing certificate for $DOMAIN..."
$COMPOSE run --rm --entrypoint certbot certbot renew --quiet

CERT="$ROOT/config/certbot/certs/live/$DOMAIN/fullchain.pem"
if [ -f "$CERT" ]; then
    sudo cp "$ROOT/config/certbot/certs/live/$DOMAIN/fullchain.pem" "$ROOT/config/certs/nginx.crt"
    sudo cp "$ROOT/config/certbot/certs/live/$DOMAIN/privkey.pem"   "$ROOT/config/certs/nginx.key"
    sudo chown "$(id -u):$(id -g)" "$ROOT/config/certs/nginx.crt" "$ROOT/config/certs/nginx.key"
    docker exec odoo17-nginx nginx -s reload
    echo "Certificate renewed and nginx reloaded."
else
    echo "No certificate found at $CERT — renewal may have been skipped (not yet due)."
fi
