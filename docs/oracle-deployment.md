# Oracle Cloud Deployment Guide

## Prerequisites

- Oracle Cloud VM (Ubuntu 22.04+ recommended)
- Docker and Docker Compose installed
- Domain name pointed to VM's public IP
- Open ports: 80 (HTTP), 443 (HTTPS), 5678 (n8n)

## Step 1: SSH into VM

```bash
ssh ubuntu@your-vm-ip
```

## Step 2: Install Docker

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker ubuntu
newgrp docker
```

## Step 3: Clone Project

```bash
cd /opt
git clone <repo-url> project-monitor
cd project-monitor
```

## Step 4: Configure Environment

```bash
cp .env.production.example .env.production
nano .env.production
```

Set these critical values:
- `POSTGRES_PASSWORD` — strong random password
- `JWT_SECRET` — `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `API_SECRET_KEY` — `python3 -c "import secrets; print(secrets.token_hex(16))"`
- `DOMAIN_NAME` — your domain (e.g., `monitor.example.com`)

## Step 5: Deploy

```bash
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

## Step 6: Setup SSL

```bash
# Initial certificate (standalone mode)
docker compose --env-file .env.production -f docker-compose.production.yml run --rm certbot certonly \
    --webroot --webroot-path=/var/www/certbot \
    --email admin@your-domain.com --agree-tos --no-eff-email \
    -d your-domain.com

# Restart nginx to use certificate
docker compose --env-file .env.production -f docker-compose.production.yml exec nginx nginx -s reload
```

Certbot auto-renews every 12 hours via the certbot container.

## Step 7: Setup Backups

```bash
# Add to crontab
crontab -e
# Add line:
0 2 * * * /opt/project-monitor/scripts/backup-db.sh >> /var/log/backup.log 2>&1
```

## Step 8: Enable Auto-Start

```bash
sudo cp scripts/project-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable project-monitor
sudo systemctl start project-monitor
```

## Step 9: Verify

```bash
# Check all services
docker compose --env-file .env.production -f docker-compose.production.yml ps

# Check API
curl https://your-domain.com/health

# Check self-monitoring
TOKEN=$(curl -s -X POST "https://your-domain.com/api/v1/auth/login?email=admin@monitor.com&password=admin123" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
curl -H "Authorization: Bearer $TOKEN" https://your-domain.com/api/v1/system/health/detailed
```

## Oracle Cloud Security List

Open these ports in Oracle Cloud console:
- **80/tcp** — HTTP (redirects to HTTPS)
- **443/tcp** — HTTPS (main access)
- **5678/tcp** — n8n (optional, public)

## Troubleshooting

```bash
# Check logs
docker compose --env-file .env.production -f docker-compose.production.yml logs -f monitoring-agent
docker compose --env-file .env.production -f docker-compose.production.yml logs -f nginx

# Restart services
docker compose --env-file .env.production -f docker-compose.production.yml restart

# Rebuild
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```
