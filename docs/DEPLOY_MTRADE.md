# Deploy Guide – MTrade

**Domain:** `MTrade.molido.shop`  
**Bot:** set `TELEGRAM_BOT_TOKEN` only in server `.env` (never git).

> Broker credentials: enter only in the web UI / server `.env` — never commit to git.

---

## 0) Security first

1. If a Telegram or GitHub token was pasted in chat, **revoke it** and create a new one. Put the new value only in server `.env`.
2. Open only ports: `22`, `80`, `443`.
3. Create a non-root sudo user for deploy.
4. Do not commit VPS IPs, chat IDs, or tokens to this repo.

---

## 1) DNS

Point `MTrade.molido.shop` A record to your VPS public IP.

```bash
dig +short MTrade.molido.shop
```

---

## 2) On the VPS (SSH)

```bash
ssh youruser@<VPS_IP>
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
git checkout enable-live-and-harden-compose   # or main after merge
```

### Environment file

```bash
cp .env.example .env
nano .env
```

Set at least:

```env
APP_ENV=production
DEBUG=false
SECRET_KEY=<openssl rand -hex 32>
POSTGRES_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-password>
TRADING_ACCOUNT_MODE=REAL
MASTER_BOT_ENABLED=true
TELEGRAM_BOT_TOKEN=<NEW_TOKEN>
TELEGRAM_ADMIN_CHAT_ID=<ADMIN_CHAT_ID>
TELEGRAM_ALLOWED_CHAT_IDS=<comma-separated-ids>
MT5_REAL_LOGIN=
MT5_REAL_PASSWORD=
MT5_REAL_SERVER=
```

```bash
openssl rand -hex 32
```

---

## 3) Start services

```bash
cd /opt/molido/Molido-Trade-Bot-Ai
docker compose up -d --build
curl -s http://127.0.0.1:8000/api/v1/health
```

---

## 4) Nginx + HTTPS

Use `infra/nginx/molido.conf` as a starting point. Terminate TLS with certbot on `MTrade.molido.shop`.

---

## 5) Verify

- [ ] Dashboard loads
- [ ] `/api/v1/health` returns JSON
- [ ] Telegram `/status` works only for allowed chat IDs
- [ ] First dashboard user is admin; later registration is closed in production
- [ ] `POST /api/v1/ops/*` returns 401 without admin JWT
- [ ] No secrets, IPs, or chat IDs in git
