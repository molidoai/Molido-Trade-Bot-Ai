from fastapi import APIRouter
from app.api.v1 import system, auth, metrics, ops, settings, brain

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(metrics.router, tags=["metrics"])
api_router.include_router(ops.router, tags=["ops"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(brain.router, tags=["brain"])
