from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "healthy",
        "service": settings.app_name,
    }


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ready",
        "service": settings.app_name,
        "environment": settings.app_env,
    }
