from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.stats import router as stats_router
from app.api.routes.webhooks import router as webhook_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.job_worker import get_job_worker

settings = get_settings()
job_worker = get_job_worker()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings.log_level)
    logger = logging.getLogger("app.main")
    job_worker.start()
    logger.info(
        "Application startup complete | service=%s environment=%s",
        settings.app_name,
        settings.app_env,
    )
    yield
    job_worker.stop()
    logger.info("Application shutdown")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(stats_router)
app.include_router(webhook_router)
