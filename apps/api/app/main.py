"""
Molido Trade Bot AI - FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.api.v1 import api_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting {settings.app_name}")
    print(f"Environment     : {settings.app_env}")
    print(f"Account Mode    : {settings.trading_account_mode}")
    print(f"Master Bot      : {'ON' if settings.master_bot_enabled else 'OFF'}")
    print(f"Debug           : {settings.debug}")
    yield
    print("Shutting down gracefully...")


app = FastAPI(
    title=settings.app_name,
    description=(
        "Professional Automated Forex Trading Platform.\n\n"
        "**Disclaimer**: This software does not guarantee profits "
        "and is not financial advice. Trading involves substantial risk of loss."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    return JSONResponse(
        content={
            "message": f"Welcome to {settings.app_name}",
            "version": "0.1.0",
            "docs": "/docs" if not settings.is_production else "disabled in production",
            "health": f"{settings.api_prefix}/health",
            "disclaimer": (
                "This platform does not guarantee profits. "
                "Trading involves substantial risk of loss."
            ),
        }
    )
