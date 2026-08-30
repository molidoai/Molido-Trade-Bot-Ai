#!/usr/bin/env bash
# Quick start script for local API development (without full Docker)

set -e
cd "$(dirname "$0")/../apps/api"

export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export SECRET_KEY="${SECRET_KEY:-dev-secret-key-change-me-in-production-32chars}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-changeme}"
export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
export DEBUG=true
export APP_ENV=development
export TRADING_ACCOUNT_MODE=DEMO
export MASTER_BOT_ENABLED=false

echo "Starting Molido Trade Bot AI API..."
echo "Account Mode: DEMO (safe default)"
echo "Master Bot  : OFF (safe default)"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
