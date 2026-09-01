"""
Molido Trade Bot AI - FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.api.v1 import api_router

try:
    from molido_security.checks import check_env_safety
except ImportError:  # pragma: no cover
    check_env_safety = None  # type: ignore

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting {settings.app_name}")
    print(f"Environment     : {settings.app_env}")
    print(f"Account Mode    : {settings.trading_account_mode}")
    print(f"Master Bot      : {'ON' if settings.master_bot_enabled else 'OFF'}")
    print(f"Live            : {'YES' if settings.is_real_account and settings.master_bot_enabled else 'NO'}")
    print(f"Debug           : {settings.debug}")
    if check_env_safety is not None:
        report = check_env_safety()
        for w in report.warnings:
            logger.warning("env safety: %s", w)
        for f in report.findings:
            logger.error("env safety: %s", f)
        if not report.ok and settings.is_production:
            raise RuntimeError(
                "Refusing to start in production with unsafe env config: "
                + "; ".join(report.findings)
            )
    yield
    print("Shutting down gracefully...")


app = FastAPI(
    title=settings.app_name,
    description=(
        "Professional Automated Forex Trading Platform.\n\n"
        "**Disclaimer**: This software does not guarantee profits "
        "and is not financial advice. Trading involves substantial risk of loss."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    return JSONResponse(
        content={
            "message": f"Welcome to {settings.app_name}",
            "version": "0.2.0",
            "account_mode": settings.trading_account_mode,
            "master_bot": settings.master_bot_enabled,
            "live": settings.is_real_account and settings.master_bot_enabled,
            "docs": "/docs" if not settings.is_production else "disabled in production",
            "health": f"{settings.api_prefix}/health",
            "disclaimer": (
                "This platform does not guarantee profits. "
                "Trading involves substantial risk of loss."
            ),
        }
    )
