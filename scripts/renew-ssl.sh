#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
compose=(docker compose --env-file .env.production -f docker-compose.production.yml)
"${compose[@]}" run --rm --no-deps certbot renew --webroot -w /var/www/certbot
"${compose[@]}" exec -T nginx nginx -s reload
