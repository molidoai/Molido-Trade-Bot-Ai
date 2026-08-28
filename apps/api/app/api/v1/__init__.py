from fastapi import APIRouter
from app.api.v1 import system, auth, metrics

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(metrics.router, tags=["metrics"])
