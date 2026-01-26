"""API v1 package initialization."""

from fastapi import APIRouter

from app.api.v1.research import router as research_router
from app.api.v1.history import router as history_router
from app.api.v1.status import router as status_router
from app.api.v1.health import router as health_router

api_router = APIRouter()

api_router.include_router(research_router, prefix="/research", tags=["research"])
api_router.include_router(history_router, prefix="/history", tags=["history"])
api_router.include_router(status_router, prefix="/status", tags=["status"])
api_router.include_router(health_router, prefix="/health", tags=["health"])

__all__ = ["api_router"]
