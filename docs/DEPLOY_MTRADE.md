# Deploy Guide – MTrade.molido.shop

**Server:** `141.94.45.232`  
**Domain:** `MTrade.molido.shop`  
**Bot:** `@MolidoTrade_bot`

> Demo RoboForex credentials: enter only in the web UI / server `.env` — never commit to git.

---

## 0) Security first

1. The Telegram bot token was shared in chat → **revoke it in BotFather** (`/revoke`) and create a **new** token, then put only the new one in server `.env`.
2. Open only ports: `22`, `80`, `443` (and optionally `8000` temporarily for debug).
3. Create a non-root sudo user for deploy.

---

## 1) DNS

In your DNS panel for `molido.shop`:

| Type | Name   | Value          |
|------|--------|----------------|
| A    | MTrade | 141.94.45.232  |

Wait until:

```bash
dig +short MTrade.molido.shop
# should print 141.94.45.232
```

---

## 2) On the VPS (SSH)

```bash
ssh root@141.94.45.232
# or: ssh youruser@141.94.45.232
```

### Install Docker

```bash
apt update && apt install -y git curl ca-certificates
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin
```

### Clone project

```bash
mkdir -p /opt/molido && cd /opt/molido
git clone https://github.com/molidoai/Molido-Trade-Bot-Ai.git
cd Molido-Trade-Bot-Ai
```

### Environment file

```bash
cp .env.example .env
nano .env
```

Set at least:

```env
APP_NAME=Molido Trade Bot AI
APP_ENV=production
DEBUG=false
SECRET_KEY=<generate-with: openssl rand -hex 32>
API_PREFIX=/api/v1

POSTGRES_USER=molido
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=molido_trading
POSTGRES_HOST=postgres

REDIS_HOST=redis

TRADING_ACCOUNT_MODE=DEMO
MASTER_BOT_ENABLED=false

TELEGRAM_BOT_TOKEN=<NEW_TOKEN_FROM_BOTFATHER>
TELEGRAM_ADMIN_CHAT_ID=1471119931
TELEGRAM_ALLOWED_CHAT_IDS=1471119931,6994702413

# Leave empty until you enter Demo in UI / later:
MT5_DEMO_LOGIN=
MT5_DEMO_PASSWORD=
MT5_DEMO_SERVER=
```

Generate secret:

```bash
openssl rand -hex 32
```

---

## 3) Start core services

```bash
cd /opt/molido/Molido-Trade-Bot-Ai
docker compose up -d postgres redis
docker compose up -d --build api
```

Check:

```bash
curl -s http://127.0.0.1:8000/api/v1/health
```

---

## 4) Nginx + HTTPS

```bash
apt install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/mtrade`:

```nginx
server {
    listen 80;
    server_name MTrade.molido.shop;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
ln -sf /etc/nginx/sites-available/mtrade /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d MTrade.molido.shop
```

---

## 5) Frontend

```bash
cd /opt/molido/Molido-Trade-Bot-Ai/frontend
# Node 20+
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
npm install
export NEXT_PUBLIC_API_URL=https://MTrade.molido.shop/api/v1
npm run build
# simple run (or put behind pm2):
npm run start -- -p 3000
```

Or use `pm2`:

```bash
npm i -g pm2
pm2 start "npm run start -- -p 3000" --name molido-web
pm2 save
```

---

## 6) Telegram bot on server

```bash
cd /opt/molido/Molido-Trade-Bot-Ai/telegram-bot
pip install -e . httpx
export TELEGRAM_BOT_TOKEN='...'
export TELEGRAM_ADMIN_CHAT_ID='1471119931'
export TELEGRAM_ALLOWED_CHAT_IDS='1471119931,6994702413'
python -m molido_telegram.bot
```

Prefer `pm2` or a systemd unit so it restarts on reboot.

Test in Telegram: open `https://t.me/MolidoTrade_bot` → `/start` from Admin1 or Admin2.

---

## 7) RoboForex Demo

You said you will enter Demo yourself on the site:

1. Keep `TRADING_ACCOUNT_MODE=DEMO`
2. Keep `MASTER_BOT_ENABLED=false` until checks pass
3. After MT5 terminal is available on the server (or remote), fill `MT5_DEMO_*`
4. Run reconcile + one Paper/Demo cycle before enabling Master ON

---

## 8) Verify checklist

- [ ] `https://MTrade.molido.shop` loads dashboard
- [ ] `https://MTrade.molido.shop/api/v1/health` returns JSON
- [ ] Telegram `/status` works for both admin IDs
- [ ] Non-admin chat IDs are ignored
- [ ] Mode is DEMO, Master OFF
- [ ] No secrets in git

---

## What I still need from you to go further remotely

- SSH access method: password or public key (you can add my key only if you want remote install)
- Confirmation that DNS A record points to `141.94.45.232`
- New Telegram token after revoke (do not paste in public GitHub issues)
