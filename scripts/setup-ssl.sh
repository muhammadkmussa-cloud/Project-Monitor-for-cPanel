#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
DOMAIN="${1:?Usage: setup-ssl.sh domain email}"
EMAIL="${2:?Usage: setup-ssl.sh domain email}"
export DOMAIN_NAME="$DOMAIN"
compose=(docker compose --env-file .env.production -f docker-compose.production.yml)
# Initial certificate issuance needs port 80 free. Other services stay running.
"${compose[@]}" stop nginx
"${compose[@]}" run --rm --no-deps -p 80:80 certbot certonly --standalone \
    --email "$EMAIL" --agree-tos --no-eff-email -d "$DOMAIN"
"${compose[@]}" up -d nginx
