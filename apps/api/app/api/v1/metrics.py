"""Prometheus metrics endpoint."""

from fastapi import APIRouter, Response

router = APIRouter()

try:
    from molido_observability import metrics as registry
except ImportError:
    registry = None


@router.get("/metrics")
async def prometheus_metrics():
    if registry is None:
        return Response(
            content="# molido observability package not installed\n",
            media_type="text/plain",
        )
    return Response(content=registry.render(), media_type="text/plain; version=0.0.4")
