from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings.log_level)
    logger = logging.getLogger("app.main")
    logger.info(
        "Application startup complete | service=%s environment=%s",
        settings.app_name,
        settings.app_env,
    )
    yield
    logger.info("Application shutdown")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)
app.include_router(health_router)
